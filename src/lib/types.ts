export type Confidence = "hoch" | "mittel" | "niedrig";
export type SourceState = "ok" | "error" | "not_configured";
export interface Evidence { source: "solana_rpc" | "market_provider" | "enhanced_transaction_provider"; detail: string; reference?: string }
export interface TokenIdentity { name: string | null; symbol: string | null; mint: string; program: "SPL Token" | "Token-2022"; isToken2022: boolean; supply: string; decimals: number; logoUrl: string | null }
export interface TokenAuthorities { mintAuthority: string | null; mintRevoked: boolean; freezeAuthority: string | null; freezeRevoked: boolean }
export interface TokenExtensionAnalysis { type: string; explanation: string; authority: string | null; configuration: Record<string,string|number|boolean|null>; risk: "info"|"warning"|"critical" }
export interface Holder { address: string; owner: string | null; amount: string; percentage: number; classification: string | null; classificationConfidence: Confidence | null }
export interface HolderAnalysis { raw: Holder[]; adjusted: Holder[]; top1: number; top5: number; top10: number; top20: number; note: string }
export interface MarketPeriod { priceChange: number | null; volume: number | null; buys: number | null; sells: number | null }
export interface PoolAnalysis { address: string; dex: string; pair: string; liquidityUsd: number | null; liquidityShare: number | null; createdAt: string | null; volume24h: number | null; volumeLiquidityRatio: number | null }
export interface MarketMetrics { priceUsd: number | null; priceSol: number | null; liquidityUsd: number | null; fdv: number | null; marketCap: number | null; periods: Record<"m5"|"h1"|"h6"|"h24",MarketPeriod>; pools: PoolAnalysis[] }
export interface CreatorInference { address: string | null; confidence: Confidence; evidence: Evidence[]; note: string }
export type RiskCategory = "CONTROL"|"HOLDERS"|"LIQUIDITY"|"TOKEN_MECHANICS"|"MARKET"|"CREATOR_BEHAVIOR";
export type FindingStatus = "critical"|"warning"|"ok"|"unknown";
export interface RiskFinding { id:string; title:string; category:RiskCategory; weight:number; status:FindingStatus; measuredValue:string|null; explanation:string; evidence:Evidence[]; dataAvailable:boolean }
export interface RiskAssessment { score:number; category:string; coverage:number; confidence:Confidence; reliable:boolean; findings:RiskFinding[] }
export interface SourceStatus { provider:string; status:SourceState; updatedAt:string; message?:string }
export interface TokenAnalysisResult { token:TokenIdentity; authorities:TokenAuthorities; extensions:TokenExtensionAnalysis[]; holders:HolderAnalysis|null; market:MarketMetrics|null; creator:CreatorInference; routeability:{status:"unknown";note:string}; risk:RiskAssessment; metadata:{analyzedAt:string;sources:SourceStatus[];warnings:string[];demo:boolean} }
export interface AnalysisSnapshot { mint:string; name:string|null; symbol:string|null; priceUsd:number|null; liquidityUsd:number|null; riskScore:number; coverage:number; top10:number|null; mintRevoked:boolean; freezeRevoked:boolean; analyzedAt:string }
