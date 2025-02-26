from pymongo import MongoClient

client = MongoClient("mongodb+srv://msm98:paras123@cluster0.4gnmc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

db = client['food']

collection = db['products']

users = db['users']

cart_collection = db['cart']