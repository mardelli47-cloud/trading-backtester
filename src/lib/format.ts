export const money=(value:number|null)=>value==null?"Nicht verfügbar":new Intl.NumberFormat("de-DE",{style:"currency",currency:"USD",maximumFractionDigits:value<.01?9:2}).format(value);
export const percent=(value:number|null)=>value==null?"Nicht verfügbar":new Intl.NumberFormat("de-DE",{maximumFractionDigits:1}).format(value)+" %";
export const localTime=(value:string)=>new Intl.DateTimeFormat("de-DE",{dateStyle:"medium",timeStyle:"medium"}).format(new Date(value));
