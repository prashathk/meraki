export const token = () => sessionStorage.getItem('meraki_token') || '';
export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  if(import.meta.env.VITE_FIREBASE_CONFIG && import.meta.env.VITE_FIREBASE_CONFIG!=='{}' && token()){
    const {firebaseAuth}=await import('./firebase');const current=firebaseAuth().currentUser;if(current)sessionStorage.setItem('meraki_token',await current.getIdToken());
  }
  const response = await fetch('/api' + path, { ...options, headers: { ...(options.body instanceof FormData ? {} : {'Content-Type':'application/json'}), ...(token() ? {Authorization:'Bearer '+token()} : {}), ...options.headers } });
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(typeof error.detail==='string'?error.detail:JSON.stringify(error.detail || 'Request failed')); }
  return response.json();
}
export async function downloadReport(id:string) {
  const response=await fetch('/api/recommendations/'+id+'/report',{headers:{Authorization:'Bearer '+token()}});
  if(!response.ok)throw new Error('Unable to download this report');
  const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download='Meraki-shortlist.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export type Tag={id:string;label:string;type:string};
export type Course={id:string;course_id:string;title:string;university:string;faculty:string;tags:string[];course_url:string;match?:number;matched_tags?:string[];mode?:string;duration?:string;evidence?:string;state?:string;revision?:number;source_id?:string;review_comment?:string;illustrative?:boolean;org:string;owner:string;url_mode?:string;reviewed?:boolean};
