import { PublicKey } from "@solana/web3.js";
export function parseMintAddress(input:string):PublicKey|null{try{const value=input.trim();if(!value)return null;const key=new PublicKey(value);return key.toBase58()===value?key:null}catch{return null}}
export function shortenAddress(value:string){return value.length>12?`${value.slice(0,4)}...${value.slice(-4)}`:value}
export function explorerAddress(value:string){return `https://explorer.solana.com/address/${encodeURIComponent(value)}`}
