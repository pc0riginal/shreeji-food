from fastapi import (
    FastAPI,
    Request,
    Query,
    UploadFile,
    Form,
    HTTPException,
    status,
    Depends,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi_login import LoginManager
from typing import Optional
from datetime import timedelta
import models
from db import collection, users, cart_collection
import os
import shutil
from urllib.parse import quote

# Constants
SECRET_KEY = "e4bd6393dd6b40d8952c4a1e9755970a8b393c2b4742dcdea82e3f86c3b76199"  # Change this in production!
ACCESS_TOKEN_EXPIRE_MINUTES = 60
ACCESS_TOKEN_EXPIRE = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

# Initialize the app
app = FastAPI()

# Template & Static File
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Image store folder
image_folder = os.path.join("static", "images")
os.makedirs(image_folder, exist_ok=True)

# Fast-api Login Manager
login_manager = LoginManager(secret=SECRET_KEY, token_url="/login", use_cookie=True)
login_manager.cookie_name = "auth_token"
login_manager.default_expiry = ACCESS_TOKEN_EXPIRE


@login_manager.user_loader()
def load_user(email: str):
    user_data = users.find_one({"email": email})
    if not user_data:
        return RedirectResponse("/login", status_code=302)

    try:
        return models.User(**user_data)
    except Exception as e:
        print(f"Error loading user: {e}")
        return None  # Avoid breaking if there's a schema mismatch


@app.get("/auth/status")
def get_current_user(user: models.User = Depends(login_manager)):
    return {"user": user.email if user else None}


@app.get("/signup", response_class=HTMLResponse)
def signup(req: Request):
    return templates.TemplateResponse("signup.html", {"request": req, "user": None})


@app.post("/signup")
async def signup(
    req: Request,
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
):
    existing_user = users.find_one({"email": email})
    if existing_user:
        return templates.TemplateResponse(
            "signup.html", {"request": req, "error": "User Alredy Registered!"}
        )
    new_user = models.User(email=email, username=username, password=password)
    new_user.hash_password()

    users.insert_one(new_user.dict())
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login(req: Request):
    return templates.TemplateResponse("login.html", {"request": req})


@app.post("/login")
async def login(req: Request, email: str = Form(...), password: str = Form(...)):
    user = load_user(email)
    if not user:
        return templates.TemplateResponse(
            "login.html", {"request": req, "error": "User not found"}
        )

    if not user.verify_password(password):
        return templates.TemplateResponse(
            "login.html", {"request": req, "error": "Invalid Credential"}
        )

    access_token = login_manager.create_access_token(data={"sub": email})
    res = RedirectResponse("/products", status_code=302)
    login_manager.set_cookie(res, access_token)
    return res


@app.get("/logout")
def logout(req: Request):
    res = RedirectResponse("/login", status_code=302)
    res.delete_cookie("auth_token")
    return res


@app.get("/")
def root(req: Request):
    return RedirectResponse("/products", status_code=302)


@app.get("/products", response_class=HTMLResponse)
def get_products(req: Request, page: int = Query(1, ge=1)):
    per_page = 12
    skip = (page - 1) * per_page

    total_products = collection.count_documents({})
    total_pages = (total_products + per_page - 1) // per_page
    has_next = total_products > skip + per_page
    has_previous = page > 1

    res = []
    products = list(
        collection.find({}, {"_id": 0})
        .sort("product_id", -1)
        .skip(skip)
        .limit(per_page)
    )

    for product in products:
        res.append({str(product["product_id"]): product})

    return templates.TemplateResponse(
        "index.html",
        {
            "request": req,
            "products": res,
            "title": "Product List",
            "page": page,
            "total_pages": total_pages,
        },
    )


@app.get("/create", response_class=HTMLResponse)
def create_product(req: Request):
    return templates.TemplateResponse("create.html", {"request": req})


@app.post("/products", response_class=RedirectResponse)
async def add_product(
    req: Request,
    product_image: UploadFile = Form(...),
    name: Optional[str] = Form(...),
    price: Optional[int] = Form(...),
    quantity: Optional[str] = Form(...),
):

    image_filename = os.path.join(image_folder, product_image.filename)
    with open(image_filename, "wb") as buffer:
        shutil.copyfileobj(product_image.file, buffer)

    last_product = collection.find_one(sort=[("product_id", -1)])
    new_product_id = last_product["product_id"] + 1 if last_product else 1

    new_product = {
        "product_id": new_product_id,
        "image": product_image.filename,
        "name": name,
        "price": price,
        "quantity": quantity,
    }

    if not new_product:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No products to be added"
        )

    collection.insert_one(new_product)
    return RedirectResponse("/products", status_code=302)


@app.get("/add-to-cart")
def add_to_cart(
    req: Request,
    product_id: int = Query(...),
    user: models.User = Depends(login_manager),
):
    if not user:
        raise HTTPException(
            status_code=401, detail="You must be logged in to add items to the cart"
        )

    user_cart = cart_collection.find_one({"user_email": user.email}) or {"items": {}}

    if str(product_id) in user_cart["items"]:
        user_cart["items"][str(product_id)]["quantity"] += 1
    else:
        product = collection.find_one({"product_id": product_id}, {"_id": 0})
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        user_cart["items"][str(product_id)] = {
            "name": product["name"],
            "price": product["price"],
            "image": product["image"],
            "quantity": 1,
        }

    cart_collection.update_one(
        {"user_email": user.email}, {"$set": {"items": user_cart["items"]}}, upsert=True
    )
    return {"message": f"Product {product_id} added to cart by {user}"}


async def get_current_user(req: Request):
    """Retrieve the logged-in user or redirect to login page."""
    try:
        user = await login_manager(req)  # Use await for async
        if not user:
            return RedirectResponse("/login", status_code=302)
        return user
    except Exception as e:
        print(f"LoginManager Error: {str(e)}")
        return RedirectResponse("/login", status_code=302)


def generate_order_summary(cart):
    order_summary = "🛒 *Order Summary*:\n"  # %0A%0A for double new lines
    total_price = 0

    for product_id, product in cart.get("items", {}).items():
        item_total = product["quantity"] * product["price"]
        total_price += item_total
        order_summary += f"🔹 *{product['name']}*  \n {product['quantity']} x ₹{product['price']} = ₹{item_total} \n"

    order_summary += f"💰 *Total Amount:* ₹{total_price}"

    return quote(order_summary)  # Encode message for URL


@app.get("/cart", response_class=HTMLResponse)
async def view_cart(req: Request, user: models.User = Depends(get_current_user)):
    if isinstance(user, RedirectResponse):  # If redirected, return immediately
        return user

    cart = cart_collection.find_one({"user_email": user.email}) or {"items": {}}
    total_price = sum(
        product["price"] * product["quantity"] for product in cart["items"].values()
    )

    order_summary = generate_order_summary(cart)

    return templates.TemplateResponse(
        "cart.html",
        {
            "request": req,
            "cart": cart,
            "total_price": total_price,
            "title": "Cart",
            "order_summary": order_summary,
            "whatsapp_number": "+917016254510",
        },
    )


@app.get("/update-cart")
async def update_cart(
    req: Request,
    product_id: int = Query(...),
    action: str = Query(...),
    user: models.User = Depends(get_current_user),
):
    if isinstance(user, RedirectResponse):  # If redirected, return immediately
        return user

    cart = cart_collection.find_one({"user_email": user.email} or {"items": {}})

    if str(product_id) not in cart["items"]:
        raise HTTPException(status_code=404, detail="Product not in cart")

    if action == "increase":
        cart["items"][str(product_id)]["quantity"] += 1
    elif action == "decrease":
        cart["items"][str(product_id)]["quantity"] -= 1
        if cart["items"][str(product_id)]["quantity"] <= 0:
            del cart["items"][str(product_id)]

    cart_collection.update_one(
        {"user_email": user.email}, {"$set": {"items": cart["items"]}}, upsert=True
    )

    return RedirectResponse("/cart", status_code=302)


@app.get("/remove-from-cart")
async def update_cart(
    req: Request,
    product_id: int = Query(...),
    user: models.User = Depends(get_current_user),
):
    if isinstance(user, RedirectResponse):  # If redirected, return immediately
        return user

    cart = cart_collection.find_one({"user_email": user.email} or {"items": {}})

    if str(product_id) not in cart["items"]:
        raise HTTPException(status_code=404, detail="Product not in cart")

    del cart["items"][str(product_id)]

    cart_collection.update_one(
        {"user_email": user.email}, {"$set": {"items": cart["items"]}}, upsert=True
    )

    return RedirectResponse("/cart", status_code=302)

@app.get("/clear-cart", response_class=HTMLResponse)
async def clear_cart(req: Request, user: models.User = Depends(get_current_user)):
    if isinstance(user, RedirectResponse):  # If redirected, return immediately
        return user

    # Clear cart in the database
    cart_collection.update_one({"user_email": user.email}, {"$set": {"items": {}}})

    # Show thank-you message
    return templates.TemplateResponse(
        "thank_you.html",
        {"request": req, "title": "Thank You"},
    )
