import {initializeApp,getApps} from 'firebase/app';
import {getAuth,signInWithEmailAndPassword,createUserWithEmailAndPassword,sendEmailVerification,sendPasswordResetEmail,GoogleAuthProvider,signInWithPopup} from 'firebase/auth';
export function firebaseAuth(){
 const config=JSON.parse(import.meta.env.VITE_FIREBASE_CONFIG||'{}');
 if(!config.apiKey)throw new Error('Firebase client configuration is missing');
 return getAuth(getApps()[0]||initializeApp(config));
}
export async function firebaseLogin(email:string,password:string,signup:boolean,google=false){
 const auth=firebaseAuth();const credential=google?await signInWithPopup(auth,new GoogleAuthProvider()):signup?await createUserWithEmailAndPassword(auth,email,password):await signInWithEmailAndPassword(auth,email,password);
 if(!credential.user.emailVerified){await sendEmailVerification(credential.user);throw new Error('Verification email sent. Verify your email, then log in again.');}
 return credential.user.getIdToken(true);
}
export async function resetPassword(email:string){await sendPasswordResetEmail(firebaseAuth(),email);}
