export type AgeException={ecosystem:string;package:string;version:string;expires:number;reason:string};
export type Policy={minimum_age_days:number;overrides:AgeException[]};
export function parsePolicy(value:unknown):Policy {
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error('Package policy is unavailable. Please retry.');
 const data=value as Record<string,unknown>;
 if(typeof data.minimum_age_days!=='number'||!Number.isFinite(data.minimum_age_days)||data.minimum_age_days<0)throw Error('Package policy is incomplete. Please retry.');
 const overrides=Array.isArray(data.overrides)?data.overrides.filter((x):x is AgeException=>Boolean(x&&typeof x==='object'&&['ecosystem','package','version','reason'].every(k=>typeof x[k]==='string')&&Number.isFinite(x.expires))):[];
 return {minimum_age_days:data.minimum_age_days,overrides};
}
