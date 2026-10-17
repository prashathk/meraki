"""Initial aggregate records and indexed versioned graph edges."""
from alembic import op
from backend.meraki.db import Base
revision='001'
down_revision=None
branch_labels=None
depends_on=None
def upgrade():Base.metadata.create_all(op.get_bind())
def downgrade():raise RuntimeError('Automatic destructive downgrade disabled. Restore a verified backup instead.')
