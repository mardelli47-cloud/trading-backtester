import type { AnalysisSnapshot } from "./types";const KEY="meme-radar-watchlist-v1",LIMIT=30;
export interface WatchItem{mint:string;snapshots:AnalysisSnapshot[]}
export function readWatchlist():WatchItem[]{if(typeof window==="undefined")return[];try{return JSON.parse(localStorage.getItem(KEY)??"[]") as WatchItem[]}catch{return[]}}
export function saveSnapshot(snapshot:AnalysisSnapshot){const list=readWatchlist();const old=list.find(x=>x.mint===snapshot.mint);if(old)old.snapshots=[...old.snapshots,snapshot].slice(-LIMIT);else list.push({mint:snapshot.mint,snapshots:[snapshot]});localStorage.setItem(KEY,JSON.stringify(list));}
export function removeWatch(mint:string){localStorage.setItem(KEY,JSON.stringify(readWatchlist().filter(x=>x.mint!==mint)))}
