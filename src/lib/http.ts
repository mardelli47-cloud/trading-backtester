export async function fetchWithPolicy(url:string, init:RequestInit={}, attempts=3):Promise<Response>{
  let last:unknown;
  for(let attempt=0;attempt<attempts;attempt++){
    const controller=new AbortController(); const timer=setTimeout(()=>controller.abort(),8_000);
    try{ const response=await fetch(url,{...init,signal:controller.signal}); if(response.ok)return response; if(response.status<500&&response.status!==429)throw new Error(`HTTP ${response.status}`); last=new Error(`HTTP ${response.status}`); }
    catch(error){last=error;} finally{clearTimeout(timer);}
    if(attempt+1<attempts) await new Promise(resolve=>setTimeout(resolve,250*2**attempt));
  }
  throw last instanceof Error?last:new Error("Datenquelle nicht erreichbar");
}
