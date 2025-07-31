import { SSHTunnelConfig } from "./proxy";
import * as fs from "fs";
import * as path from "path";

export interface SSHConfig {
  sshHost: string;
  sshPort: number;
  sshUsername: string;
  sshPassword: string;
}

export interface ConfigFile {
  sshConfig: SSHConfig;
  tunnels: SSHTunnelConfig[];
}

export function loadConfigFromFile(configPath: string = "config.json"): SSHTunnelConfig[] {
  try {
    // Check if config file exists
    if (!fs.existsSync(configPath)) {
      console.error(`❌ Config file not found: ${configPath}`);
      console.log("📝 Please create a config.json file or use config-template.json as a template");
      return [];
    }

    // Read and parse config file
    const configContent = fs.readFileSync(configPath, "utf8");
    const config: ConfigFile = JSON.parse(configContent);

    // Validate config structure
    if (!config.sshConfig || !config.tunnels) {
      console.error("❌ Invalid config structure. Missing sshConfig or tunnels");
      return [];
    }

    // Merge SSH config with each tunnel config
    const configList: SSHTunnelConfig[] = config.tunnels.map(tunnel => ({
      ...config.sshConfig,
      ...tunnel
    }));

    console.log(`✅ Loaded ${configList.length} tunnel configurations from ${configPath}`);
    return configList;

  } catch (error) {
    console.error(`❌ Error loading config from ${configPath}:`, error);
    return [];
  }
}

export function loadConfig(): SSHTunnelConfig[] {
  // Try to load from environment variable first
  const envConfigPath = process.env.PHANTOM_CONFIG_FILE;
  if (envConfigPath) {
    return loadConfigFromFile(envConfigPath);
  }

  // Try default config.json
  const defaultConfig = loadConfigFromFile("config.json");
  if (defaultConfig.length > 0) {
    return defaultConfig;
  }

  // Fallback to hardcoded config (for backward compatibility)
  console.log("⚠️  No config file found, using fallback configuration");
  return getFallbackConfig();
}

function getFallbackConfig(): SSHTunnelConfig[] {
  const sshConf = {
    sshHost: "10.54.18.150",
    sshPort: 22,
    sshUsername: "suropati",
    sshPassword: "Sur0p4t1#",
  };

  return [
    {
      ...sshConf,
      name: "DB 142",
      remoteHost: "10.54.18.142",
      remotePort: 5432,
      localPort: 54142,
      autoReconnect: true,
    },
    {
      ...sshConf,
      name: "DB 54",
      remoteHost: "10.54.18.54",
      remotePort: 5432,
      localPort: 5454,
      autoReconnect: true,
    },
    {
      ...sshConf,
      name: "DB 235",
      remoteHost: "10.54.18.235",
      remotePort: 5432,
      localPort: 54235,
      autoReconnect: true,
    },
    {
      ...sshConf,
      name: "Bypass",
      remoteHost: "localhost",
      remotePort: 1081,
      localPort: 1081,
      enableDynamicSocks5: true,
      dynamicSocks5Port: 10801,
    },
  ];
} 