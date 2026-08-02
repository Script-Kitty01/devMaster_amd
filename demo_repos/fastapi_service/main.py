"""
FastAPI microservice — contains intentional performance, security,
and architecture issues for ForgeAI multi-agent analysis.
"""
import os
import hashlib
import requests
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from pymongo import MongoClient
import redis

app = FastAPI(title="User Service")

# SECURITY: Hardcoded credentials
MONGO_URI = "mongodb://admin:superpass123@localhost:27017"
REDIS_URL = "redis://:redispass@localhost:6379"

# PERFORMANCE: Global connection — no pooling, no timeout
mongo = MongoClient(MONGO_URI)
cache = redis.from_url(REDIS_URL)

# SECURITY: Weak password hashing
def hash_pw(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()

# PERFORMANCE: No index on email field — full collection scan
@app.get("/users/by-email")
def get_user_by_email(email: str = Query(...)):
    user = mongo.app_db.users.find_one({"email": email})
    if not user:
        raise HTTPException(404, "User not found")
    user["_id"] = str(user["_id"])
    return user

# PERFORMANCE: N+1 query problem
@app.get("/users/{user_id}/orders")
def get_user_orders(user_id: str):
    user = mongo.app_db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(404, "User not found")
    orders = []
    # N+1: fetches each order individually
    for order_id in user.get("order_ids", []):
        order = mongo.app_db.orders.find_one({"_id": order_id})
        if order:
            order["_id"] = str(order["_id"])
            orders.append(order)
    return {"user_id": user_id, "orders": orders}

# SECURITY: SSRF vulnerability — user-controlled URL
@app.get("/fetch")
def fetch_url(url: str = Query(...)):
    resp = requests.get(url, timeout=5)
    return {"status": resp.status_code, "body": resp.text[:500]}

# PERFORMANCE: No caching on expensive endpoint
@app.get("/stats")
def get_stats():
    total_users = mongo.app_db.users.count_documents({})
    total_orders = mongo.app_db.orders.count_documents({})
    # PERFORMANCE: Aggregation without pipeline optimization
    pipeline = [
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    result = list(mongo.app_db.orders.aggregate(pipeline))
    revenue = result[0]["total"] if result else 0
    return {"users": total_users, "orders": total_orders, "revenue": revenue}

# ARCHITECTURE: Monolithic — all routes in one file
# SECURITY: No authentication middleware
# PERFORMANCE: No connection retry logic

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
