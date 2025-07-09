import { configList } from "./config";

import { logger, colorize, sshTunnelService, TunnelInfo, SSHTunnelConfig } from "./proxy";

// Function to format table for logger
function formatTunnelTable(tunnelData: TunnelInfo[]): void {
  if (tunnelData.length === 0) {
    logger.warn(
      colorize("[PHANTOM]", "No phantom nodes detected in the network")
    );
    return;
  }

  // Column headers and widths
  const headers = [
    "NODE NAME",
    "LOCAL HOST",
    "LOCAL PORT",
    "REMOTE HOST",
    "REMOTE PORT",
    "SOCKS5",
    "DYNAMIC SOCKS5",
    "STATUS",
  ];

  const colWidths: number[] = [20, 15, 12, 20, 12, 10, 15, 12];
  const totalWidth = colWidths.reduce((sum, width) => sum + width + 3, 1); // +3 for borders and spacing

  const border = "═".repeat(totalWidth - 2);
  const separator = "─".repeat(totalWidth - 2);

  // Header
  logger.info(colorize("[PHANTOM]", "╔" + border + "╗"));
  logger.info(
    colorize(
      "[PHANTOM]",
      "║" +
        " ".repeat(Math.floor((totalWidth - 2 - 31) / 2)) +
        ">>> PHANTOM NETWORK STATUS <<<" +
        " ".repeat(Math.ceil((totalWidth - 2 - 31) / 2)) +
        "║"
    )
  );
  logger.info(colorize("[PHANTOM]", "╠" + separator + "╣"));

  // Column headers
  let headerRow = "║";
  headers.forEach((header, i) => {
    const width = colWidths[i] ?? 0;
    const padding = Math.max(0, width - header.length);
    const leftPad = Math.floor(padding / 2);
    const rightPad = padding - leftPad;
    headerRow += " ".repeat(leftPad) + header + " ".repeat(rightPad) + " ║";
  });

  logger.info(colorize("[PHANTOM]", headerRow));
  logger.info(colorize("[PHANTOM]", "╠" + separator + "╣"));

  // Data rows
  tunnelData.forEach((tunnel, index) => {
    // Check if this tunnel has SOCKS5 enabled by looking at the original config
    const originalConfig = configList.find(c => c.name === tunnel.name);
    const hasSocks5 = originalConfig?.enableSocks5 || false;
    const socks5Port = hasSocks5 ? (originalConfig?.socks5Port || tunnel.localPort + 1000) : null;
    
    // Check if this tunnel has Dynamic SOCKS5 enabled
    const hasDynamicSocks5 = originalConfig?.enableDynamicSocks5 || false;
    const dynamicSocks5Port = hasDynamicSocks5 ? (originalConfig?.dynamicSocks5Port || tunnel.localPort + 2000) : null;
    
    const data = [
      tunnel.name || `phantom_${index}`,
      tunnel.localHost,
      tunnel.localPort.toString(),
      tunnel.remoteHost,
      tunnel.remotePort.toString(),
      hasSocks5 ? `:${socks5Port}` : "N/A",
      hasDynamicSocks5 ? `:${dynamicSocks5Port}` : "N/A",
      tunnel.isActive ? "🟢 ONLINE" : "🔴 OFFLINE",
    ];

    let row = "║";
    data.forEach((value, i) => {
      const width = colWidths[i] ?? 0;
      const padding = Math.max(0, width - value.length);
      const leftPad = Math.floor(padding / 2);
      const rightPad = padding - leftPad;
      row += " ".repeat(leftPad) + value + " ".repeat(rightPad) + " ║";
    });

    const statusColor = tunnel.isActive ? "[GHOST]" : "[DEAD]";
    logger.info(colorize(statusColor, row));
  });

  // Footer
  logger.info(colorize("[PHANTOM]", "╚" + border + "╝"));

  // Summary stats
  const activeCount = tunnelData.filter((t) => t.isActive).length;
  const totalCount = tunnelData.length;
  const socks5Count = configList.filter(c => c.enableSocks5).length;
  const dynamicSocks5Count = configList.filter(c => c.enableDynamicSocks5).length;

  logger.info(
    colorize(
      "[PHANTOM]",
      `>>> NETWORK SUMMARY: ${activeCount}/${totalCount} phantom nodes operational (${socks5Count} SOCKS5 gateways, ${dynamicSocks5Count} Dynamic SOCKS5 gateways)`
    )
  );
  if (activeCount === totalCount) {
    logger.info(
      colorize(
        "[GHOST]",
        ">>> ALL SYSTEMS OPERATIONAL - NETWORK FULLY INFILTRATED"
      )
    );
  } else if (activeCount === 0) {
    logger.info(
      colorize("[DEAD]", ">>> NETWORK COMPROMISED - ALL PHANTOM NODES OFFLINE")
    );
  } else {
    logger.info(
      colorize(
        "[DANGER]",
        ">>> PARTIAL INFILTRATION - SOME PHANTOM NODES COMPROMISED"
      )
    );
  }
}

// Alternative compact table format
function formatCompactTunnelTable(tunnelData: TunnelInfo[]): void {
  if (tunnelData.length === 0) {
    logger.warn(
      colorize("[PHANTOM]", "No phantom nodes detected in the network")
    );
    return;
  }

  logger.info(
    colorize(
      "[PHANTOM]",
      "┌─────────────────────── PHANTOM NETWORK STATUS ───────────────────────┐"
    )
  );

  tunnelData.forEach((tunnel, index) => {
    const status = tunnel.isActive ? "🟢 ONLINE" : "🔴 OFFLINE";
    const nodeName = tunnel.name || `phantom_${index}`;
    const route = `${tunnel.localHost}:${tunnel.localPort} → ${tunnel.remoteHost}:${tunnel.remotePort}`;
    
    // Check for SOCKS5
    const originalConfig = configList.find(c => c.name === tunnel.name);
    const hasSocks5 = originalConfig?.enableSocks5 || false;
    const socks5Info = hasSocks5 ? ` [SOCKS5:${originalConfig?.socks5Port || tunnel.localPort + 1000}]` : "";

    logger.info(
      colorize(
        tunnel.isActive ? "[GHOST]" : "[DEAD]",
        `│ ${nodeName.padEnd(20)} │ ${(route + socks5Info).padEnd(45)} │ ${status} │`
      )
    );
  });

  logger.info(
    colorize(
      "[PHANTOM]",
      "└───────────────────────────────────────────────────────────────────────┘"
    )
  );
}

// Enhanced version of your original code
(async () => {
  logger.info(
    colorize("[INJECT]", "Initiating phantom network deployment protocol...")
  );

  let tunnelTable: TunnelInfo[] = [];

  for (const config of configList) {
    try {
      // Validate required properties
      if (!config.remoteHost || !config.remotePort || !config.localPort) {
        logger.error(
          colorize(
            "[BREACH]",
            `Invalid configuration for tunnel '${config.name}': missing required properties (remoteHost, remotePort, localPort)`
          )
        );
        continue;
      }

      const tunnelInfo = await sshTunnelService.createTunnel(config);
      tunnelTable.push(tunnelInfo);

      // Log each successful tunnel creation
      logger.info(
        colorize(
          "[GHOST]",
          `Phantom node '${tunnelInfo.name}' infiltrated: ${tunnelInfo.localHost}:${tunnelInfo.localPort} → ${tunnelInfo.remoteHost}:${tunnelInfo.remotePort}`
        )
      );

      // Log SOCKS5 information if enabled
      if (config.enableSocks5) {
        const socks5Port = config.socks5Port || config.localPort + 1000;
        logger.info(
          colorize(
            "[SHADOW]",
            `SOCKS5 gateway activated for '${tunnelInfo.name}' on localhost:${socks5Port}`
          )
        );
      }

      // Log Dynamic SOCKS5 information if enabled
      if (config.enableDynamicSocks5) {
        const dynamicSocks5Port = config.dynamicSocks5Port || config.localPort + 2000;
        logger.info(
          colorize(
            "[SHADOW]",
            `Dynamic SOCKS5 gateway activated for '${tunnelInfo.name}' on localhost:${dynamicSocks5Port} `
          )
        );
      }
    } catch (error) {
      logger.error(
        colorize(
          "[BREACH]",
          `Failed to deploy phantom node '${config.name}' for ${config.remoteHost}:${config.remotePort}`
        ),
        error
      );
    }
  }

  // Display the formatted table through logger
  logger.info(colorize("[PHANTOM]", "═".repeat(80)));
  formatTunnelTable(tunnelTable);
  logger.info(colorize("[PHANTOM]", "═".repeat(80)));

  // Alternative: Use compact format
  // formatCompactTunnelTable(tunnelTable);
})();

// You can also create a helper function to display current tunnel status anytime
export function displayPhantomNetworkStatus(): void {
  const activeTunnels = sshTunnelService.getActiveTunnels();
  const allTunnels = sshTunnelService.getAllTunnels();

  logger.info(
    colorize("[PHANTOM]", "Scanning phantom network for active nodes...")
  );

  const tunnelInfoArray: TunnelInfo[] = allTunnels
    .filter((tunnel) => tunnel.info)
    .map((tunnel) => tunnel.info!);

  formatTunnelTable(tunnelInfoArray);
}
