import { SSHTunnelConfig } from "./proxy";
import { loadConfig } from "./config-loader";

// Load configuration from file or use fallback
export const configList: SSHTunnelConfig[] = loadConfig();
