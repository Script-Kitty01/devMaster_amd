/**
 * Express API — contains intentional security & architecture issues
 * for Kutaar multi-agent analysis.
 */
const express = require("express");
const jwt = require("jsonwebtoken");
const mysql = require("mysql");
const cors = require("cors");

const app = express();
app.use(cors());
app.use(express.json());

// SECURITY: Hardcoded JWT secret
const JWT_SECRET = "my-super-secret-key-123";

// SECURITY: Hardcoded DB credentials
const db = mysql.createConnection({
  host: "localhost",
  user: "root",
  password: "password123",
  database: "app_db",
});

// SECURITY: SQL injection — string interpolation
app.get("/users", (req, res) => {
  const { name } = req.query;
  const query = `SELECT * FROM users WHERE name = '${name}'`;
  db.query(query, (err, results) => {
    if (err) return res.status(500).json({ error: err.message });
    res.json(results);
  });
});

// SECURITY: No rate limiting on login
app.post("/login", (req, res) => {
  const { username, password } = req.body;
  // SECURITY: Plain-text password comparison
  const query = `SELECT * FROM users WHERE username = '${username}' AND password = '${password}'`;
  db.query(query, (err, results) => {
    if (err || results.length === 0) {
      return res.status(401).json({ error: "Invalid credentials" });
    }
    // SECURITY: Weak JWT — no expiry, no audience
    const token = jwt.sign({ username }, JWT_SECRET);
    res.json({ token });
  });
});

// PERFORMANCE: No pagination — returns all rows
app.get("/logs", (req, res) => {
  db.query("SELECT * FROM access_logs", (err, results) => {
    if (err) return res.status(500).json({ error: err.message });
    res.json(results);
  });
});

// ARCHITECTURE: All logic in one file, no separation of concerns
// SECURITY: No input validation
app.post("/transfer", (req, res) => {
  const { from, to, amount } = req.body;
  db.query(
    `UPDATE accounts SET balance = balance - ${amount} WHERE id = ${from}`,
    () => {},
  );
  db.query(
    `UPDATE accounts SET balance = balance + ${amount} WHERE id = ${to}`,
    () => {},
  );
  res.json({ status: "ok" });
});

// SECURITY: Stack trace exposure in errors
app.use((err, req, res, next) => {
  res.status(500).json({ error: err.stack });
});

app.listen(3000, () => console.log("Server running on port 3000"));
