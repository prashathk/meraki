terraform {

  required_version = ">= 1.7"
  required_providers {

    google = {

      source = "hashicorp/google", version = "~> 6.0"
    }

  }


}

provider "google" {

  project = var.project_id
  region  = var.region

}

variable "project_id" {

  type = string
}

variable "region" {

  type    = string
  default = "us-central1"

}

variable "image" {

  type        = string
  description = "Immutable Artifact Registry image URI produced by Cloud Build"

}

variable "gemini_model" {

  type = string
}

variable "database_secret_id" {

  type        = string
  description = "Existing Secret Manager secret holding PostgreSQL SQLAlchemy URL, using /cloudsql socket"

}

variable "database_user_password" {

  type        = string
  sensitive   = true
  description = "Bootstrap DB password; protect Terraform state. Match the manually populated database URL secret."

}

variable "web_origin" {

  type        = string
  description = "Exact HTTPS frontend origin, no trailing slash"

}

locals {

  services = toset(["run.googleapis.com", "sqladmin.googleapis.com", "artifactregistry.googleapis.com", "secretmanager.googleapis.com", "cloudtasks.googleapis.com", "aiplatform.googleapis.com", "identitytoolkit.googleapis.com", "cloudbuild.googleapis.com", "storage.googleapis.com"])
}

resource "google_project_service" "api" {

  for_each           = local.services
  service            = each.value
  disable_on_destroy = false

}

resource "google_service_account" "app" {

  account_id   = "meraki-app"
  display_name = "Meraki application"

}

resource "google_service_account" "task" {

  account_id   = "meraki-task-dispatch"
  display_name = "Meraki task identity"

}

resource "google_project_iam_member" "app_roles" {

  for_each = toset(["roles/cloudsql.client", "roles/aiplatform.user", "roles/cloudtasks.enqueuer", "roles/firebaseauth.viewer"])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.app.email}"

}

resource "google_service_account_iam_member" "dispatch_as_task" {

  service_account_id = google_service_account.task.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.app.email}"

}

resource "google_secret_manager_secret_iam_member" "database" {

  project   = var.project_id
  secret_id = var.database_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app.email}"

}

resource "google_storage_bucket" "private" {

  name                        = "${var.project_id}-meraki-private"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  versioning {

    enabled = true
  }

  force_destroy = false

}

resource "google_storage_bucket_iam_member" "objects" {

  bucket = google_storage_bucket.private.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.app.email}"

}

resource "google_artifact_registry_repository" "images" {

  location      = var.region
  repository_id = "meraki"
  format        = "DOCKER"
  depends_on    = [google_project_service.api]

}

resource "google_sql_database_instance" "postgres" {

  name                = "meraki-postgres"
  region              = var.region
  database_version    = "POSTGRES_17"
  deletion_protection = true
  settings {

    tier              = "db-custom-1-3840"
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 20
    backup_configuration {

      enabled                        = true
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7

    }

    ip_configuration {

      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"

    }


  }

  depends_on = [google_project_service.api]

}

resource "google_sql_database" "db" {

  name     = "meraki"
  instance = google_sql_database_instance.postgres.name

}

resource "google_sql_user" "app" {

  name     = "meraki"
  instance = google_sql_database_instance.postgres.name
  password = var.database_user_password

}

resource "google_cloud_tasks_queue" "extract" {

  name     = "meraki-extraction"
  location = var.region
  rate_limits {

    max_concurrent_dispatches = 3
    max_dispatches_per_second = 1

  }

  retry_config {

    max_attempts  = 5
    min_backoff   = "10s"
    max_backoff   = "300s"
    max_doublings = 4

  }

  depends_on = [google_project_service.api]

}

resource "google_cloud_run_v2_service" "worker" {

  name                = "meraki-worker"
  location            = var.region
  deletion_protection = true
  template {

    service_account                  = google_service_account.app.email
    timeout                          = "600s"
    max_instance_request_concurrency = 1
    scaling {

      max_instance_count = 3
    }

    volumes {

      name = "cloudsql"
      cloud_sql_instance {

        instances = [google_sql_database_instance.postgres.connection_name]
      }


    }

    containers {

      image   = var.image
      command = ["python", "-m", "uvicorn", "worker.api:app", "--host", "0.0.0.0", "--port", "8080"]
      resources {

        limits = {

          cpu = "1", memory = "1Gi"
        }

      }

      volume_mounts {

        name       = "cloudsql"
        mount_path = "/cloudsql"

      }

      env {

        name  = "APP_ENV"
        value = "production"

      }

      env {

        name  = "AUTH_PROVIDER"
        value = "firebase"

      }

      env {

        name = "DATABASE_URL"
        value_source {
          secret_key_ref {

            secret  = var.database_secret_id
            version = "latest"

          }

        }


      }

      env {

        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id

      }

      env {

        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region

      }

      env {

        name  = "GEMINI_MODEL"
        value = var.gemini_model

      }

      env {

        name  = "STORAGE_BUCKET"
        value = google_storage_bucket.private.name

      }


    }


  }

  depends_on = [google_project_service.api, google_sql_user.app, google_secret_manager_secret_iam_member.database]

}

resource "google_cloud_run_v2_service_iam_member" "worker_invoker" {

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.worker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.task.email}"

}

resource "google_cloud_run_v2_service" "api" {

  name                = "meraki-api"
  location            = var.region
  deletion_protection = true
  template {

    service_account                  = google_service_account.app.email
    timeout                          = "60s"
    max_instance_request_concurrency = 20
    scaling {

      max_instance_count = 5
    }

    volumes {

      name = "cloudsql"
      cloud_sql_instance {

        instances = [google_sql_database_instance.postgres.connection_name]
      }


    }

    containers {

      image = var.image
      resources {

        limits = {

          cpu = "1", memory = "512Mi"
        }

      }

      volume_mounts {

        name       = "cloudsql"
        mount_path = "/cloudsql"

      }

      env {

        name  = "APP_ENV"
        value = "production"

      }

      env {

        name  = "AUTH_PROVIDER"
        value = "firebase"

      }

      env {

        name = "DATABASE_URL"
        value_source {
          secret_key_ref {

            secret  = var.database_secret_id
            version = "latest"

          }

        }


      }

      env {

        name  = "STORAGE_BUCKET"
        value = google_storage_bucket.private.name

      }

      env {

        name  = "CORS_ORIGINS"
        value = var.web_origin

      }

      env {

        name  = "TASKS_QUEUE"
        value = google_cloud_tasks_queue.extract.id

      }

      env {

        name  = "WORKER_URL"
        value = google_cloud_run_v2_service.worker.uri

      }

      env {

        name  = "TASKS_SERVICE_ACCOUNT"
        value = google_service_account.task.email

      }


    }


  }

  depends_on = [google_project_service.api, google_sql_user.app, google_secret_manager_secret_iam_member.database]

}

resource "google_cloud_run_v2_service_iam_member" "public_api" {

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"

}

output "api_url" {

  value = google_cloud_run_v2_service.api.uri
}

output "worker_url" {

  value = google_cloud_run_v2_service.worker.uri
}

output "sql_connection_name" {

  value = google_sql_database_instance.postgres.connection_name
}

