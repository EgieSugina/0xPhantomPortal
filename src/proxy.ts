import { Client as SSHClient, ConnectConfig } from "ssh2";
import { createServer, Server, Socket } from "net";
import { EventEmitter } from "events";
import log4js from "log4js";
import chalk from "chalk";

// Configure log4js
log4js.configure({
  appenders: {
    console: { type: "console" },
    file: { type: "file", filename: "phantom-portal.log" },
  },
  categories: {
    default: { appenders: ["console", "file"], level: "info" },
  },
});

export const logger = log4js.getLogger("0xPhantomPortal");

// Helper function to colorize log messages with dark web aesthetic
export function colorize(type: string, message: string): string {
  const timestamp = new Date().toISOString().replace("T", " ").slice(0, 19);
  const prefix = chalk.dim(`[${timestamp}]`);

  switch (type) {
    case "[BREACH]":
      return (
        prefix +
        " " +
        chalk.red.bold("◢◤") +
        " " +
        chalk.red(type) +
        " " +
        chalk.white(message)
      );
    case "[INJECT]":
      return (
        prefix +
        " " +
        chalk.cyan.bold("⚡") +
        " " +
        chalk.cyan(type) +
        " " +
        chalk.white(message)
      );
    case "[GHOST]":
      return (
        prefix +
        " " +
        chalk.green.bold("👻") +
        " " +
        chalk.green(type) +
        " " +
        chalk.white(message)
      );
    case "[SHADOW]":
      return (
        prefix +
        " " +
        chalk.magenta.bold("🌙") +
        " " +
        chalk.magenta(type) +
        " " +
        chalk.white(message)
      );
    case "[ONLINE]":
      return (
        prefix +
        " " +
        chalk.green.bold("●") +
        " " +
        chalk.green(type) +
        " " +
        chalk.white(message)
      );
    case "[DANGER]":
      return (
        prefix +
        " " +
        chalk.yellow.bold("⚠") +
        " " +
        chalk.yellow(type) +
        " " +
        chalk.white(message)
      );
    case "[DEAD]":
      return (
        prefix +
        " " +
        chalk.red.bold("💀") +
        " " +
        chalk.red(type) +
        " " +
        chalk.white(message)
      );
    case "[RETRY]":
      return (
        prefix +
        " " +
        chalk.yellow.bold("🔄") +
        " " +
        chalk.yellow(type) +
        " " +
        chalk.white(message)
      );
    case "[REVIVE]":
      return (
        prefix +
        " " +
        chalk.green.bold("⚡") +
        " " +
        chalk.green(type) +
        " " +
        chalk.white(message)
      );
    case "[NUKE]":
      return (
        prefix +
        " " +
        chalk.red.bold("💥") +
        " " +
        chalk.red(type) +
        " " +
        chalk.white(message)
      );
    case "[PHANTOM]":
      return (
        prefix +
        " " +
        chalk.dim.bold("🔒") +
        " " +
        chalk.dim(type) +
        " " +
        chalk.white(message)
      );
    default:
      return prefix + " " + chalk.gray(type) + " " + chalk.white(message);
  }
}

/**
 * Configure SSH Tunnel Service logging
 * @param config log4js configuration object
 */
export function configureSSHTunnelLogging(config: log4js.Configuration): void {
  log4js.configure(config);
}

/**
 * Get the SSH Tunnel logger instance
 * @returns log4js logger instance
 */
export function getSSHTunnelLogger(): log4js.Logger {
  return logger;
}

export interface SSHTunnelConfig {
  sshHost: string;
  sshPort: number;
  sshUsername: string;
  sshPassword?: string | undefined;
  sshPrivateKey?: string | undefined;
  sshPassphrase?: string | undefined;
  remoteHost: string;
  remotePort: number;
  localPort: number;
  autoReconnect?: boolean | undefined;
  maxReconnectAttempts?: number | undefined;
  reconnectDelay?: number | undefined;
  name?: string | undefined;
  // SOCKS5 configuration
  enableSocks5?: boolean | undefined;
  socks5Port?: number | undefined;
  socks5Host?: string | undefined;
  socks5Auth?: {
    username?: string | undefined;
    password?: string | undefined;
  } | undefined;
  // Dynamic SOCKS5 tunneling (like ssh -D)
  enableDynamicSocks5?: boolean | undefined;
  dynamicSocks5Port?: number | undefined;
  dynamicSocks5Host?: string | undefined;
}

export interface TunnelInfo {
  localHost: string;
  localPort: number;
  remoteHost: string;
  remotePort: number;
  isActive: boolean;
  name?: string | undefined;
}

export interface SSHTunnelEvents {
  connected: (tunnelInfo: TunnelInfo) => void;
  disconnected: (tunnelInfo: TunnelInfo) => void;
  error: (error: Error, tunnelName?: string) => void;
  reconnecting: (attempt: number, tunnelName?: string) => void;
  reconnected: (tunnelInfo: TunnelInfo) => void;
}

declare interface SSHTunnelManager {
  on<U extends keyof SSHTunnelEvents>(
    event: U,
    listener: SSHTunnelEvents[U]
  ): this;
  emit<U extends keyof SSHTunnelEvents>(
    event: U,
    ...args: Parameters<SSHTunnelEvents[U]>
  ): boolean;
}

// SOCKS5 protocol constants
const SOCKS5_VERSION = 0x05;
const SOCKS5_AUTH_METHODS = {
  NO_AUTH: 0x00,
  USERNAME_PASSWORD: 0x02,
  NO_ACCEPTABLE: 0xff,
};
const SOCKS5_COMMANDS = {
  CONNECT: 0x01,
  BIND: 0x02,
  UDP_ASSOCIATE: 0x03,
};
const SOCKS5_ADDRESS_TYPES = {
  IPV4: 0x01,
  DOMAIN: 0x03,
  IPV6: 0x04,
};
const SOCKS5_REPLY_CODES = {
  SUCCESS: 0x00,
  GENERAL_FAILURE: 0x01,
  CONNECTION_NOT_ALLOWED: 0x02,
  NETWORK_UNREACHABLE: 0x03,
  HOST_UNREACHABLE: 0x04,
  CONNECTION_REFUSED: 0x05,
  TTL_EXPIRED: 0x06,
  COMMAND_NOT_SUPPORTED: 0x07,
  ADDRESS_TYPE_NOT_SUPPORTED: 0x08,
};

// SOCKS5 server implementation
class SOCKS5Server {
  private server: Server;
  private sshClient: SSHClient;
  private config: SSHTunnelConfig;

  constructor(sshClient: SSHClient, config: SSHTunnelConfig) {
    this.sshClient = sshClient;
    this.config = config;
    this.server = createServer();
    this.setupServer();
  }

  private setupServer(): void {
    this.server.on("connection", (socket: Socket) => {
      this.handleConnection(socket);
    });
  }

  private async handleConnection(socket: Socket): Promise<void> {
    try {
      // Handle SOCKS5 handshake
      await this.handleHandshake(socket);
    } catch (error) {
      logger.error(
        colorize("[BREACH]", "SOCKS5 handshake failed - connection terminated:"),
        error
      );
      socket.destroy();
    }
  }

  private async handleHandshake(socket: Socket): Promise<void> {
    return new Promise((resolve, reject) => {
      const onData = (data: Buffer) => {
        socket.removeListener("data", onData);
        socket.removeListener("error", onError);

        try {
          // Parse SOCKS5 handshake
          if (data.length < 3) {
            reject(new Error("Invalid SOCKS5 handshake"));
            return;
          }

          const version = data[0];
          const numMethods = data[1];
          const methods = data.slice(2, 2 + (numMethods || 0));

          if (version !== SOCKS5_VERSION) {
            reject(new Error("Unsupported SOCKS version"));
            return;
          }

          // Check if authentication is required
          const hasAuth = this.config.socks5Auth?.username && this.config.socks5Auth?.password;
          const supportsNoAuth = methods.includes(SOCKS5_AUTH_METHODS.NO_AUTH);
          const supportsUserPass = methods.includes(SOCKS5_AUTH_METHODS.USERNAME_PASSWORD);

          let authMethod = SOCKS5_AUTH_METHODS.NO_AUTH;
          if (hasAuth && supportsUserPass) {
            authMethod = SOCKS5_AUTH_METHODS.USERNAME_PASSWORD;
          } else if (!supportsNoAuth && !supportsUserPass) {
            authMethod = SOCKS5_AUTH_METHODS.NO_ACCEPTABLE;
          }

          // Send handshake response
          const response = Buffer.from([SOCKS5_VERSION, authMethod]);
          socket.write(response);

          if (authMethod === SOCKS5_AUTH_METHODS.NO_ACCEPTABLE) {
            reject(new Error("No acceptable authentication method"));
            return;
          }

          if (authMethod === SOCKS5_AUTH_METHODS.USERNAME_PASSWORD) {
            this.handleUserPassAuth(socket).then(resolve).catch(reject);
          } else {
            this.handleRequest(socket).then(resolve).catch(reject);
          }
        } catch (error) {
          reject(error);
        }
      };

      const onError = (error: Error) => {
        socket.removeListener("data", onData);
        socket.removeListener("error", onError);
        reject(error);
      };

      socket.once("data", onData);
      socket.once("error", onError);
    });
  }

  private async handleUserPassAuth(socket: Socket): Promise<void> {
    return new Promise((resolve, reject) => {
      const onData = (data: Buffer) => {
        socket.removeListener("data", onData);
        socket.removeListener("error", onError);

        try {
          if (data.length < 3) {
            reject(new Error("Invalid username/password auth"));
            return;
          }

          const version = data[0];
          const usernameLength = data[1];
          const username = data.slice(2, 2 + (usernameLength || 0)).toString();
          const passwordLength = data[2 + (usernameLength || 0)];
          const password = data.slice(3 + (usernameLength || 0), 3 + (usernameLength || 0) + (passwordLength || 0)).toString();

          const expectedUsername = this.config.socks5Auth?.username;
          const expectedPassword = this.config.socks5Auth?.password;

          if (username === expectedUsername && password === expectedPassword) {
            // Send success response
            const response = Buffer.from([0x01, 0x00]);
            socket.write(response);
            this.handleRequest(socket).then(resolve).catch(reject);
          } else {
            // Send failure response
            const response = Buffer.from([0x01, 0x01]);
            socket.write(response);
            reject(new Error("Authentication failed"));
          }
        } catch (error) {
          reject(error);
        }
      };

      const onError = (error: Error) => {
        socket.removeListener("data", onData);
        socket.removeListener("error", onError);
        reject(error);
      };

      socket.once("data", onData);
      socket.once("error", onError);
    });
  }

  private async handleRequest(socket: Socket): Promise<void> {
    return new Promise((resolve, reject) => {
      const onData = (data: Buffer) => {
        socket.removeListener("data", onData);
        socket.removeListener("error", onError);

        try {
          if (data.length < 7) {
            reject(new Error("Invalid SOCKS5 request"));
            return;
          }

          const version = data[0];
          const command = data[1];
          const reserved = data[2];
          const addressType = data[3];

          if (version !== SOCKS5_VERSION) {
            reject(new Error("Unsupported SOCKS version"));
            return;
          }

          if (command !== SOCKS5_COMMANDS.CONNECT) {
            this.sendReply(socket, SOCKS5_REPLY_CODES.COMMAND_NOT_SUPPORTED);
            reject(new Error("Unsupported command"));
            return;
          }

          let targetHost: string;
          let targetPort: number;
          let offset = 4;

          switch (addressType) {
            case SOCKS5_ADDRESS_TYPES.IPV4:
              if (data.length < offset + 4 + 2) {
                reject(new Error("Invalid IPv4 address"));
                return;
              }
              targetHost = data.slice(offset, offset + 4).join(".");
              offset += 4;
              break;

            case SOCKS5_ADDRESS_TYPES.DOMAIN:
              if (data.length < offset + 1) {
                reject(new Error("Invalid domain length"));
                return;
              }
              const domainLength = data[offset];
              offset += 1;
              if (data.length < offset + (domainLength || 0) + 2) {
                reject(new Error("Invalid domain"));
                return;
              }
              targetHost = data.slice(offset, offset + (domainLength || 0)).toString();
              offset += (domainLength || 0);
              break;

            case SOCKS5_ADDRESS_TYPES.IPV6:
              if (data.length < offset + 16 + 2) {
                reject(new Error("Invalid IPv6 address"));
                return;
              }
              targetHost = data.slice(offset, offset + 16).toString("hex");
              offset += 16;
              break;

            default:
              this.sendReply(socket, SOCKS5_REPLY_CODES.ADDRESS_TYPE_NOT_SUPPORTED);
              reject(new Error("Unsupported address type"));
              return;
          }

          targetPort = data.readUInt16BE(offset);

          logger.info(
            colorize(
              "[SHADOW]",
              `SOCKS5 request: ${targetHost}:${targetPort} via phantom tunnel`
            )
          );

          // Forward the connection through SSH
          this.sshClient.forwardOut(
            socket.remoteAddress!,
            socket.remotePort!,
            targetHost,
            targetPort,
            (err: Error | undefined, stream: any) => {
              if (err) {
                logger.error(
                  colorize("[BREACH]", "SOCKS5 forward failed:"),
                  err
                );
                this.sendReply(socket, SOCKS5_REPLY_CODES.HOST_UNREACHABLE);
                socket.end();
                reject(err);
                return;
              }

              // Send success reply
              this.sendReply(socket, SOCKS5_REPLY_CODES.SUCCESS);

              // Pipe data between socket and stream
              socket.pipe(stream).pipe(socket);

              stream.on("error", (error: Error) => {
                logger.error(
                  colorize("[BREACH]", "SOCKS5 stream error:"),
                  error
                );
                socket.destroy();
              });

              socket.on("error", (error: Error) => {
                logger.error(
                  colorize("[BREACH]", "SOCKS5 socket error:"),
                  error
                );
                stream.destroy();
              });

              resolve();
            }
          );
        } catch (error) {
          reject(error);
        }
      };

      const onError = (error: Error) => {
        socket.removeListener("data", onData);
        socket.removeListener("error", onError);
        reject(error);
      };

      socket.once("data", onData);
      socket.once("error", onError);
    });
  }

  private sendReply(socket: Socket, replyCode: number): void {
    const response = Buffer.from([
      SOCKS5_VERSION,
      replyCode,
      0x00, // Reserved
      0x01, // Address type (IPv4)
      0x00, 0x00, 0x00, 0x00, // IP address (0.0.0.0)
      0x00, 0x00, // Port (0)
    ]);
    socket.write(response);
  }

  public listen(port: number, host: string = "localhost"): void {
    this.server.listen(port, host, () => {
      logger.info(
        colorize(
          "[SHADOW]",
          `SOCKS5 proxy listening on ${host}:${port} - dark web gateway active`
        )
      );
    });

    this.server.on("error", (err: Error) => {
      logger.error(
        colorize("[DEAD]", "SOCKS5 proxy compromised - shutting down:"),
        err
      );
    });
  }

  public close(): void {
    this.server.close();
    logger.info(
      colorize("[NUKE]", "SOCKS5 proxy eliminated - gateway destroyed")
    );
  }
}

// Dynamic SOCKS5 server implementation (like ssh -D)
class DynamicSOCKS5Server {
  private server: Server;
  private sshClient: SSHClient;
  private config: SSHTunnelConfig;

  constructor(sshClient: SSHClient, config: SSHTunnelConfig) {
    this.sshClient = sshClient;
    this.config = config;
    this.server = createServer();
    this.setupServer();
  }

  private setupServer(): void {
    this.server.on("connection", (socket: Socket) => {
      this.handleConnection(socket);
    });
  }

  private async handleConnection(socket: Socket): Promise<void> {
    try {
      // Handle SOCKS5 handshake
      await this.handleHandshake(socket);
    } catch (error) {
      logger.error(
        colorize("[BREACH]", "Dynamic SOCKS5 handshake failed - connection terminated:"),
        error
      );
      socket.destroy();
    }
  }

  private async handleHandshake(socket: Socket): Promise<void> {
    return new Promise((resolve, reject) => {
      const onData = (data: Buffer) => {
        socket.removeListener("data", onData);
        socket.removeListener("error", onError);

        try {
          // Parse SOCKS5 handshake
          if (data.length < 3) {
            reject(new Error("Invalid SOCKS5 handshake"));
            return;
          }

          const version = data[0];
          const numMethods = data[1];
          const methods = data.slice(2, 2 + (numMethods || 0));

          if (version !== SOCKS5_VERSION) {
            reject(new Error("Unsupported SOCKS version"));
            return;
          }

          // For dynamic SOCKS5, we only support NO_AUTH
          const supportsNoAuth = methods.includes(SOCKS5_AUTH_METHODS.NO_AUTH);
          
          if (!supportsNoAuth) {
            const response = Buffer.from([SOCKS5_VERSION, SOCKS5_AUTH_METHODS.NO_ACCEPTABLE]);
            socket.write(response);
            reject(new Error("No acceptable authentication method"));
            return;
          }

          // Send handshake response - only NO_AUTH
          const response = Buffer.from([SOCKS5_VERSION, SOCKS5_AUTH_METHODS.NO_AUTH]);
          socket.write(response);

          this.handleRequest(socket).then(resolve).catch(reject);
        } catch (error) {
          reject(error);
        }
      };

      const onError = (error: Error) => {
        socket.removeListener("data", onData);
        socket.removeListener("error", onError);
        reject(error);
      };

      socket.once("data", onData);
      socket.once("error", onError);
    });
  }

  private async handleRequest(socket: Socket): Promise<void> {
    return new Promise((resolve, reject) => {
      const onData = (data: Buffer) => {
        socket.removeListener("data", onData);
        socket.removeListener("error", onError);

        try {
          if (data.length < 7) {
            reject(new Error("Invalid SOCKS5 request"));
            return;
          }

          const version = data[0];
          const command = data[1];
          const reserved = data[2];
          const addressType = data[3];

          if (version !== SOCKS5_VERSION) {
            reject(new Error("Unsupported SOCKS version"));
            return;
          }

          if (command !== SOCKS5_COMMANDS.CONNECT) {
            this.sendReply(socket, SOCKS5_REPLY_CODES.COMMAND_NOT_SUPPORTED);
            reject(new Error("Unsupported command"));
            return;
          }

          let targetHost: string;
          let targetPort: number;
          let offset = 4;

          switch (addressType) {
            case SOCKS5_ADDRESS_TYPES.IPV4:
              if (data.length < offset + 4 + 2) {
                reject(new Error("Invalid IPv4 address"));
                return;
              }
              targetHost = data.slice(offset, offset + 4).join(".");
              offset += 4;
              break;

            case SOCKS5_ADDRESS_TYPES.DOMAIN:
              if (data.length < offset + 1) {
                reject(new Error("Invalid domain length"));
                return;
              }
              const domainLength = data[offset];
              offset += 1;
              if (data.length < offset + (domainLength || 0) + 2) {
                reject(new Error("Invalid domain"));
                return;
              }
              targetHost = data.slice(offset, offset + (domainLength || 0)).toString();
              offset += (domainLength || 0);
              break;

            case SOCKS5_ADDRESS_TYPES.IPV6:
              if (data.length < offset + 16 + 2) {
                reject(new Error("Invalid IPv6 address"));
                return;
              }
              targetHost = data.slice(offset, offset + 16).toString("hex");
              offset += 16;
              break;

            default:
              this.sendReply(socket, SOCKS5_REPLY_CODES.ADDRESS_TYPE_NOT_SUPPORTED);
              reject(new Error("Unsupported address type"));
              return;
          }

          targetPort = data.readUInt16BE(offset);

          logger.info(
            colorize(
              "[SHADOW]",
              `Dynamic SOCKS5 request: ${targetHost}:${targetPort} via phantom tunnel`
            )
          );

          // Forward the connection through SSH using dynamic forwarding
          this.sshClient.forwardOut(
            socket.remoteAddress!,
            socket.remotePort!,
            targetHost,
            targetPort,
            (err: Error | undefined, stream: any) => {
              if (err) {
                logger.error(
                  colorize("[BREACH]", "Dynamic SOCKS5 forward failed:"),
                  err
                );
                this.sendReply(socket, SOCKS5_REPLY_CODES.HOST_UNREACHABLE);
                socket.end();
                reject(err);
                return;
              }

              // Send success reply
              this.sendReply(socket, SOCKS5_REPLY_CODES.SUCCESS);

              // Pipe data between socket and stream
              socket.pipe(stream).pipe(socket);

              stream.on("error", (error: Error) => {
                logger.error(
                  colorize("[BREACH]", "Dynamic SOCKS5 stream error:"),
                  error
                );
                socket.destroy();
              });

              socket.on("error", (error: Error) => {
                logger.error(
                  colorize("[BREACH]", "Dynamic SOCKS5 socket error:"),
                  error
                );
                stream.destroy();
              });

              resolve();
            }
          );
        } catch (error) {
          reject(error);
        }
      };

      const onError = (error: Error) => {
        socket.removeListener("data", onData);
        socket.removeListener("error", onError);
        reject(error);
      };

      socket.once("data", onData);
      socket.once("error", onError);
    });
  }

  private sendReply(socket: Socket, replyCode: number): void {
    const response = Buffer.from([
      SOCKS5_VERSION,
      replyCode,
      0x00, // Reserved
      0x01, // Address type (IPv4)
      0x00, 0x00, 0x00, 0x00, // IP address (0.0.0.0)
      0x00, 0x00, // Port (0)
    ]);
    socket.write(response);
  }

  public listen(port: number, host: string = "localhost"): void {
    this.server.listen(port, host, () => {
      logger.info(
        colorize(
          "[SHADOW]",
          `Dynamic SOCKS5 proxy listening on ${host}:${port} - dark web gateway active `
        )
      );
    });

    this.server.on("error", (err: Error) => {
      logger.error(
        colorize("[DEAD]", "Dynamic SOCKS5 proxy compromised - shutting down:"),
        err
      );
    });
  }

  public close(): void {
    this.server.close();
    logger.info(
      colorize("[NUKE]", "Dynamic SOCKS5 proxy eliminated - gateway destroyed")
    );
  }
}

class SSHTunnelManager extends EventEmitter {
  private sshClient?: SSHClient | undefined;
  private localServer?: Server | undefined;
  private socks5Server?: SOCKS5Server | undefined;
  private dynamicSocks5Server?: DynamicSOCKS5Server | undefined;
  private tunnelInfo?: TunnelInfo | undefined;
  private config?: SSHTunnelConfig | undefined;
  private reconnectAttempts = 0;
  private reconnectTimer?: NodeJS.Timeout | undefined;
  private isReconnecting = false;

  constructor() {
    super();
  }

  /**
   * Create SSH tunnel
   */
  public async createTunnel(config: SSHTunnelConfig): Promise<TunnelInfo> {
    this.config = { ...config };
    this.reconnectAttempts = 0;

    logger.info(
      colorize(
        "[INJECT]",
        `Initiating phantom protocol${
          config.name ? ` [${config.name}]` : ""
        } >> ${config.sshUsername}@${config.sshHost}:${config.sshPort} -> ${
          config.remoteHost
        }:${config.remotePort}`
      )
    );

    return new Promise((resolve, reject) => {
      this.sshClient = new SSHClient();

      // SSH connection options
      const sshOptions: ConnectConfig = {
        host: config.sshHost,
        port: config.sshPort,
        username: config.sshUsername,
      };

      // Add authentication method
      if (config.sshPrivateKey) {
        sshOptions.privateKey = config.sshPrivateKey;
        if (config.sshPassphrase) {
          sshOptions.passphrase = config.sshPassphrase;
        }
        logger.info(
          colorize(
            "[SHADOW]",
            "Deploying RSA cryptographic keys for stealth access"
          )
        );
      } else if (config.sshPassword) {
        sshOptions.password = config.sshPassword;
        logger.info(
          colorize(
            "[DANGER]",
            "Using plaintext auth vector - OPERATIONAL RISK DETECTED"
          )
        );
      } else {
        reject(
          new Error(
            "Authentication vector required - no credential payload detected"
          )
        );
        return;
      }

      this.sshClient.on("ready", () => {
        logger.info(
          colorize(
            "[GHOST]",
            `Phantom shell infiltration successful${
              config.name ? ` [${config.name}]` : ""
            } - we're in the mainframe`
          )
        );

        // Create local server for port forwarding
        this.localServer = createServer((socket: Socket) => {
          this.sshClient!.forwardOut(
            socket.remoteAddress!,
            socket.remotePort!,
            config.remoteHost,
            config.remotePort,
            (err: Error | undefined, stream: any) => {
              if (err) {
                logger.error(
                  colorize(
                    "[BREACH]",
                    "Data tunnel compromised - connection severed:"
                  ),
                  err
                );
                socket.end();
                return;
              }
              socket.pipe(stream).pipe(socket);
            }
          );
        });

        this.localServer.listen(config.localPort, "localhost", () => {
          this.tunnelInfo = {
            localHost: "localhost",
            localPort: config.localPort,
            remoteHost: config.remoteHost,
            remotePort: config.remotePort,
            isActive: true,
            name: config.name,
          };

          logger.info(
            colorize(
              "[SHADOW]",
              `Dark proxy listening on port ${config.localPort}${
                config.name ? ` [${config.name}]` : ""
              } - traffic rerouted through shadows`
            )
          );

          // Start SOCKS5 server if enabled
          if (config.enableSocks5) {
            const socks5Port = config.socks5Port || config.localPort + 1000;
            const socks5Host = config.socks5Host || "localhost";
            
            this.socks5Server = new SOCKS5Server(this.sshClient!, config);
            this.socks5Server.listen(socks5Port, socks5Host);
            
            logger.info(
              colorize(
                "[SHADOW]",
                `SOCKS5 gateway activated on ${socks5Host}:${socks5Port}${
                  config.name ? ` [${config.name}]` : ""
                } - dark web access granted`
              )
            );
          }

          // Start Dynamic SOCKS5 server if enabled (like ssh -D)
          if (config.enableDynamicSocks5) {
            const dynamicSocks5Port = config.dynamicSocks5Port || config.localPort + 2000;
            const dynamicSocks5Host = config.dynamicSocks5Host || "localhost";
            
            this.dynamicSocks5Server = new DynamicSOCKS5Server(this.sshClient!, config);
            this.dynamicSocks5Server.listen(dynamicSocks5Port, dynamicSocks5Host);
            
            logger.info(
              colorize(
                "[SHADOW]",
                `Dynamic SOCKS5 gateway activated on ${dynamicSocks5Host}:${dynamicSocks5Port}${
                  config.name ? ` [${config.name}]` : ""
                }`
              )
            );
          }

          logger.info(
            colorize(
              "[ONLINE]",
              `Phantom portal operational${
                config.name ? ` [${config.name}]` : ""
              } - you are now invisible`
            )
          );

          this.emit("connected", this.tunnelInfo);
          resolve(this.tunnelInfo);
        });

        this.localServer.on("error", (err: Error) => {
          logger.error(
            colorize("[DEAD]", "Local proxy node compromised - shutting down:"),
            err
          );
          this.emit("error", err, config.name);
          reject(err);
        });
      });

      this.sshClient.on("error", (err: Error) => {
        logger.error(
          colorize("[BREACH]", "SSH connection intercepted - we've been made:"),
          err
        );
        this.emit("error", err, config.name);
        if (!this.isReconnecting) {
          reject(err);
        }
      });

      this.sshClient.on("close", () => {
        logger.info(
          colorize(
            "[PHANTOM]",
            `Connection ghosted${
              config.name ? ` [${config.name}]` : ""
            } - signal lost`
          )
        );
        if (this.tunnelInfo) {
          this.tunnelInfo.isActive = false;
          this.emit("disconnected", this.tunnelInfo);
        }

        // Auto-reconnect if enabled
        if (config.autoReconnect && !this.isReconnecting) {
          this.handleAutoReconnect();
        }
      });

      this.sshClient.connect(sshOptions);
    });
  }

  /**
   * Handle automatic reconnection
   */
  private handleAutoReconnect(): void {
    if (!this.config) return;

    const maxAttempts = this.config.maxReconnectAttempts || 5;
    const delay = this.config.reconnectDelay || 5000;

    if (this.reconnectAttempts >= maxAttempts) {
      logger.error(
        colorize(
          "[DEAD]",
          `Max infiltration attempts exceeded (${maxAttempts}) - mission terminated`
        )
      );
      return;
    }

    this.reconnectAttempts++;
    this.isReconnecting = true;

    logger.info(
      colorize(
        "[RETRY]",
        `Phantom resurrection sequence initiated (${this.reconnectAttempts}/${maxAttempts}) - going dark for ${delay}ms...`
      )
    );
    this.emit("reconnecting", this.reconnectAttempts, this.config.name);

    this.reconnectTimer = setTimeout(async () => {
      try {
        await this.reconnect();
        this.isReconnecting = false;
        this.reconnectAttempts = 0;
        this.emit("reconnected", this.tunnelInfo!);
      } catch (error) {
        logger.error(
          colorize("[DEAD]", "Resurrection failed - phantom remains dead:"),
          error
        );
        this.isReconnecting = false;
        this.handleAutoReconnect();
      }
    }, delay);
  }

  /**
   * Get tunnel information
   */
  public getTunnelInfo(): TunnelInfo | undefined {
    return this.tunnelInfo;
  }

  /**
   * Check if tunnel is active
   */
  public isActive(): boolean {
    return this.tunnelInfo?.isActive ?? false;
  }

  /**
   * Reconnect tunnel if it's disconnected
   */
  public async reconnect(): Promise<TunnelInfo> {
    if (!this.config) {
      throw new Error("No phantom configuration available for resurrection");
    }

    if (this.isActive()) {
      logger.info(
        colorize(
          "[ONLINE]",
          "Phantom already operational - resurrection aborted"
        )
      );
      return this.tunnelInfo!;
    }

    logger.info(
      colorize("[REVIVE]", "Initiating phantom resurrection protocol...")
    );
    await this.close();
    return this.createTunnel(this.config);
  }

  /**
   * Close SSH tunnel
   */
  public async close(): Promise<void> {
    logger.info(
      colorize("[NUKE]", "Initiating phantom termination sequence...")
    );

    // Clear reconnection timer
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = undefined;
    }

    this.isReconnecting = false;

    // Close SOCKS5 server
    if (this.socks5Server) {
      this.socks5Server.close();
      this.socks5Server = undefined;
    }

    // Close Dynamic SOCKS5 server
    if (this.dynamicSocks5Server) {
      this.dynamicSocks5Server.close();
      this.dynamicSocks5Server = undefined;
    }

    // Close local server
    if (this.localServer) {
      return new Promise((resolve) => {
        this.localServer!.close(() => {
          logger.info(
            colorize("[NUKE]", "Dark proxy eliminated - no traces left")
          );

          // Close SSH connection
          if (this.sshClient) {
            this.sshClient.end();
            logger.info(
              colorize(
                "[PHANTOM]",
                "SSH connection severed - ghost mode activated"
              )
            );
          }

          if (this.tunnelInfo) {
            this.tunnelInfo.isActive = false;
          }

          resolve();
        });
      });
    } else if (this.sshClient) {
      this.sshClient.end();
      logger.info(
        colorize("[PHANTOM]", "SSH connection severed - ghost mode activated")
      );
    }

    if (this.tunnelInfo) {
      this.tunnelInfo.isActive = false;
    }
  }

  /**
   * Get connection details for database
   */
  public getConnectionDetails(): { host: string; port: number } | null {
    if (!this.isActive() || !this.tunnelInfo) {
      return null;
    }

    return {
      host: this.tunnelInfo.localHost,
      port: this.tunnelInfo.localPort,
    };
  }
}

/**
 * SSH Tunnel Service - Singleton service for managing multiple SSH tunnels
 */
export class SSHTunnelService {
  private static instance: SSHTunnelService;
  private tunnels: Map<string, SSHTunnelManager> = new Map();
  private defaultTunnel?: string | undefined;

  private constructor() {}

  /**
   * Get singleton instance
   */
  public static getInstance(): SSHTunnelService {
    if (!SSHTunnelService.instance) {
      SSHTunnelService.instance = new SSHTunnelService();
    }
    return SSHTunnelService.instance;
  }

  /**
   * Create a new SSH tunnel
   */
  public async createTunnel(config: SSHTunnelConfig): Promise<TunnelInfo> {
    const tunnelName =
      config.name || `phantom_${config.remoteHost}_${config.remotePort}`;

    if (this.tunnels.has(tunnelName)) {
      throw new Error(
        `Phantom node '${tunnelName}' already exists in the network`
      );
    }

    const manager = new SSHTunnelManager();
    this.tunnels.set(tunnelName, manager);

    // Set as default tunnel if it's the first one
    if (!this.defaultTunnel) {
      this.defaultTunnel = tunnelName;
    }

    // Forward events
    manager.on("connected", (info) =>
      logger.info(
        colorize(
          "[GHOST]",
          `Phantom node '${tunnelName}' infiltrated target network`
        )
      )
    );
    manager.on("disconnected", (info) =>
      logger.warn(
        colorize(
          "[DANGER]",
          `Phantom node '${tunnelName}' signal lost - connection severed`
        )
      )
    );
    manager.on("error", (error) =>
      logger.error(
        colorize("[BREACH]", `Phantom node '${tunnelName}' compromised:`),
        error
      )
    );
    manager.on("reconnecting", (attempt) =>
      logger.info(
        colorize(
          "[RETRY]",
          `Phantom node '${tunnelName}' resurrection attempt (${attempt})`
        )
      )
    );
    manager.on("reconnected", (info) =>
      logger.info(
        colorize(
          "[REVIVE]",
          `Phantom node '${tunnelName}' back online - infiltration restored`
        )
      )
    );

    const tunnelInfo = await manager.createTunnel({
      ...config,
      name: tunnelName,
    });
    return tunnelInfo;
  }

  /**
   * Get tunnel by name
   */
  public getTunnel(name?: string): SSHTunnelManager | undefined {
    const tunnelName = name || this.defaultTunnel;
    if (!tunnelName) return undefined;
    return this.tunnels.get(tunnelName);
  }

  /**
   * Get tunnel info by name
   */
  public getTunnelInfo(name?: string): TunnelInfo | undefined {
    const tunnel = this.getTunnel(name);
    return tunnel?.getTunnelInfo();
  }

  /**
   * Check if tunnel is active
   */
  public isActive(name?: string): boolean {
    const tunnel = this.getTunnel(name);
    return tunnel?.isActive() ?? false;
  }

  /**
   * Get connection details for a tunnel
   */
  public getConnectionDetails(
    name?: string
  ): { host: string; port: number } | null {
    const tunnel = this.getTunnel(name);
    return tunnel?.getConnectionDetails() ?? null;
  }

  /**
   * Close specific tunnel
   */
  public async closeTunnel(name?: string): Promise<void> {
    const tunnelName = name || this.defaultTunnel;
    if (!tunnelName) return;

    const tunnel = this.tunnels.get(tunnelName);
    if (tunnel) {
      await tunnel.close();
      this.tunnels.delete(tunnelName);

      // Update default tunnel if we closed it
      if (this.defaultTunnel === tunnelName) {
        this.defaultTunnel = this.tunnels.keys().next().value;
      }
    }
  }

  /**
   * Close all tunnels
   */
  public async closeAllTunnels(): Promise<void> {
    logger.info(
      colorize("[NUKE]", "Initiating network-wide phantom termination...")
    );
    const closePromises = Array.from(this.tunnels.values()).map((tunnel) =>
      tunnel.close()
    );
    await Promise.all(closePromises);
    this.tunnels.clear();
    this.defaultTunnel = undefined;
    logger.info(
      colorize("[PHANTOM]", "All phantom nodes eliminated - network dark")
    );
  }

  /**
   * Get all active tunnels
   */
  public getActiveTunnels(): Array<{ name: string; info: TunnelInfo }> {
    const activeTunnels: Array<{ name: string; info: TunnelInfo }> = [];

    for (const [name, tunnel] of this.tunnels) {
      const info = tunnel.getTunnelInfo();
      if (info && info.isActive) {
        activeTunnels.push({ name, info });
      }
    }

    return activeTunnels;
  }

  /**
   * Get all tunnels (active and inactive)
   */
  public getAllTunnels(): Array<{
    name: string;
    info: TunnelInfo | undefined;
  }> {
    const allTunnels: Array<{ name: string; info: TunnelInfo | undefined }> =
      [];

    for (const [name, tunnel] of this.tunnels) {
      const info = tunnel.getTunnelInfo();
      allTunnels.push({ name, info });
    }

    return allTunnels;
  }

  /**
   * Reconnect specific tunnel
   */
  public async reconnectTunnel(name?: string): Promise<TunnelInfo> {
    const tunnel = this.getTunnel(name);
    if (!tunnel) {
      throw new Error(
        `Phantom node '${name || "default"}' not found in network`
      );
    }
    return tunnel.reconnect();
  }
}

/**
 * Factory function to create SSH tunnel from environment variables
 */
export function createSSHTunnelFromEnv(
  envPrefix: string = "DB",
  localPort?: number,
  name?: string
): SSHTunnelConfig | null {
  const useSSH = process.env[`${envPrefix}_USE_SSH`] === "true";

  if (!useSSH) {
    return null;
  }

  const config: SSHTunnelConfig = {
    sshHost: process.env[`${envPrefix}_SSH_HOST`] || "localhost",
    sshPort: parseInt(process.env[`${envPrefix}_SSH_PORT`] || "22"),
    sshUsername: process.env[`${envPrefix}_SSH_USERNAME`] || "root",
    sshPassword: process.env[`${envPrefix}_SSH_PASSWORD`],
    sshPrivateKey: process.env[`${envPrefix}_SSH_PRIVATE_KEY`],
    sshPassphrase: process.env[`${envPrefix}_SSH_PASSPHRASE`],
    remoteHost: process.env[`${envPrefix}_HOST`] || "localhost",
    remotePort: parseInt(process.env[`${envPrefix}_PORT`] || "5432"),
    localPort:
      localPort || parseInt(process.env[`${envPrefix}_LOCAL_PORT`] || "15432"),
    autoReconnect: process.env[`${envPrefix}_AUTO_RECONNECT`] === "true",
    maxReconnectAttempts: parseInt(
      process.env[`${envPrefix}_MAX_RECONNECT_ATTEMPTS`] || "5"
    ),
    reconnectDelay: parseInt(
      process.env[`${envPrefix}_RECONNECT_DELAY`] || "5000"
    ),
    name: name || process.env[`${envPrefix}_TUNNEL_NAME`],
    // SOCKS5 configuration from environment
    enableSocks5: process.env[`${envPrefix}_ENABLE_SOCKS5`] === "true",
    socks5Port: process.env[`${envPrefix}_SOCKS5_PORT`] 
      ? parseInt(process.env[`${envPrefix}_SOCKS5_PORT`] || "0") 
      : undefined,
    socks5Host: process.env[`${envPrefix}_SOCKS5_HOST`],
    socks5Auth: process.env[`${envPrefix}_SOCKS5_USERNAME`] && process.env[`${envPrefix}_SOCKS5_PASSWORD`]
      ? {
          username: process.env[`${envPrefix}_SOCKS5_USERNAME`]!,
          password: process.env[`${envPrefix}_SOCKS5_PASSWORD`]!,
        }
      : undefined,
    // Dynamic SOCKS5 tunneling (like ssh -D)
    enableDynamicSocks5: process.env[`${envPrefix}_ENABLE_DYNAMIC_SOCKS5`] === "true",
    dynamicSocks5Port: process.env[`${envPrefix}_DYNAMIC_SOCKS5_PORT`] 
      ? parseInt(process.env[`${envPrefix}_DYNAMIC_SOCKS5_PORT`] || "0") 
      : undefined,
    dynamicSocks5Host: process.env[`${envPrefix}_DYNAMIC_SOCKS5_HOST`],
  };

  return config;
}

/**
 * Initialize SSH tunnel service from environment variables
 */
export async function initializeSSHTunnelFromEnv(
  envPrefix: string = "DB",
  localPort?: number,
  name?: string
): Promise<TunnelInfo | null> {
  const config = createSSHTunnelFromEnv(envPrefix, localPort, name);
  if (!config) {
    return null;
  }

  const service = SSHTunnelService.getInstance();
  return service.createTunnel(config);
}

// Export singleton instance for easy access
export const sshTunnelService = SSHTunnelService.getInstance();

// Graceful shutdown handler
process.on("SIGINT", async () => {
  logger.info(
    colorize(
      "[NUKE]",
      "\nEmergency shutdown protocol activated - burning all evidence..."
    )
  );
  await sshTunnelService.closeAllTunnels();
  log4js.shutdown(() => {
    logger.info(
      colorize("[PHANTOM]", "All traces eliminated - we were never here")
    );
    process.exit(0);
  });
});

process.on("SIGTERM", async () => {
  logger.info(
    colorize(
      "[NUKE]",
      "\nTermination signal received - executing scorched earth protocol..."
    )
  );
  await sshTunnelService.closeAllTunnels();
  log4js.shutdown(() => {
    logger.info(colorize("[PHANTOM]", "Memory wiped - phantom mode engaged"));
    process.exit(0);
  });
});
