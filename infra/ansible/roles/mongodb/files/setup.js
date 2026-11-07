// The replica set and the users, idempotently (#30). Run by roles/mongodb with the
// passwords in the environment, so none is on a command line. Prints CHANGED when it
// changed anything.
const env = process.env;
const adminDb = db.getSiblingDB("admin");
let changed = false;

function authenticates(dbName, user, password) {
  try {
    const conn = new Mongo("mongodb://127.0.0.1:" + env.MONGO_PORT + "/?directConnection=true");
    conn.getDB(dbName).auth(user, password);
    return true;
  } catch (e) {
    return false;
  }
}

// After the admin exists, the localhost exception is gone: log in first.
const adminExists = authenticates("admin", "admin", env.MONGO_ADMIN_PASSWORD);
if (adminExists) {
  adminDb.auth("admin", env.MONGO_ADMIN_PASSWORD);
}

let initiated = true;
try {
  rs.status();
} catch (e) {
  if (e.codeName !== "NotYetInitialized") throw e;
  initiated = false;
}
if (!initiated) {
  rs.initiate({ _id: env.MONGO_REPLICA_SET, members: [{ _id: 0, host: env.MONGO_MEMBER }] });
  changed = true;
}
for (let i = 0; !db.hello().isWritablePrimary; i++) {
  if (i > 60) throw new Error("no primary after 60 s");
  sleep(1000);
}

if (!adminExists) {
  adminDb.createUser({ user: "admin", pwd: env.MONGO_ADMIN_PASSWORD, roles: ["root"] });
  adminDb.auth("admin", env.MONGO_ADMIN_PASSWORD);
  changed = true;
}

function ensureUser(dbName, user, password, roles) {
  const target = db.getSiblingDB(dbName);
  if (target.getUser(user) === null) {
    target.createUser({ user: user, pwd: password, roles: roles });
    changed = true;
  } else if (!authenticates(dbName, user, password)) {
    target.updateUser(user, { pwd: password, roles: roles });
    changed = true;
  }
}

// readWrite covers collections and indexes, which migrate creates.
ensureUser(env.MONGO_INSTANCES_DB, env.MONGO_INSTANCES_USER, env.MONGO_INSTANCES_PASSWORD, [
  { role: "readWrite", db: env.MONGO_INSTANCES_DB },
]);
ensureUser("admin", "exporter", env.MONGO_EXPORTER_PASSWORD, [
  { role: "clusterMonitor", db: "admin" },
  { role: "read", db: "local" },
]);

print(changed ? "CHANGED" : "OK");
