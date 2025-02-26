from pydantic import BaseModel,EmailStr
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(BaseModel):
    email: EmailStr
    username: str
    password: str

    def hash_password(self):
        self.password = pwd_context.hash(self.password)

    def verify_password(self, plain_password):
        return pwd_context.verify(plain_password, self.password)

class Food(BaseModel):
    name : str
    price : int
    quantity : str
    product_image : str

class UserDb(User):
    hased_password : str