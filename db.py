from pymongo import MongoClient
import os
mongo_uri = os.getenv('mongo_uri')
client = MongoClient(mongo_uri)

db = client['food']

collection = db['products']

users = db['users']

cart_collection = db['cart']