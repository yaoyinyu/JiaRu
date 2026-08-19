// Minimal type declarations for Node's built-in `node:sqlite` module.
// Installed @types/node@20 does not include these; Node 24 provides the
// runtime implementation. Keep in sync with the APIs actually used in
// src/lib/auth/db.ts.
declare module "node:sqlite" {
  export interface StatementSync {
    run(...params: unknown[]): { changes: number; lastInsertRowid: number | bigint };
    get(...params: unknown[]): Record<string, unknown> | undefined;
    all(...params: unknown[]): Record<string, unknown>[];
  }

  export class DatabaseSync {
    constructor(path: string | Buffer, options?: { open?: boolean });
    exec(sql: string): void;
    prepare(sql: string): StatementSync;
    close(): void;
  }
}
