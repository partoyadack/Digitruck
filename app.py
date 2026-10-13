import os, secrets, re
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()
app = Flask(__name__, instance_relative_config=True)
os.makedirs(app.instance_path, exist_ok=True)
app.config.update(SECRET_KEY=os.getenv("SECRET_KEY", "local-change-me-" + secrets.token_hex(16)),
 SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///digitruck.db"),
 SQLALCHEMY_TRACK_MODIFICATIONS=False, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
db=SQLAlchemy(app); login=LoginManager(app); login.login_view="login"; csrf=CSRFProtect(app)
CATS=["گارد و محافظ","زیرسپر و زیرپلاکی","چراغ و روشنایی","لوازم استیل","جلوپنجره و قاب","رینگ و لاستیک","تجهیزات داخل کابین","سایر لوازم"]
STATUSES={"pending":"در انتظار بررسی","confirmed":"تأیید شده","processing":"در حال آماده‌سازی","shipped":"ارسال شده","delivered":"تحویل شده","cancelled":"لغو شده"}

class User(UserMixin,db.Model):
 id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(100),nullable=False)
 email=db.Column(db.String(180),unique=True,nullable=False,index=True); password_hash=db.Column(db.String(255),nullable=False)
 is_admin=db.Column(db.Boolean,default=False,nullable=False); created_at=db.Column(db.DateTime,default=datetime.utcnow)
 def set_password(self,p): self.password_hash=generate_password_hash(p)
 def check_password(self,p): return check_password_hash(self.password_hash,p)

class Product(db.Model):
 id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(180),nullable=False); slug=db.Column(db.String(200),unique=True,nullable=False)
 category=db.Column(db.String(100),nullable=False); brand=db.Column(db.String(80),default="عمومی")
 models=db.Column(db.String(200),default="ولوو، اسکانیا، بنز، MAN"); description=db.Column(db.Text,default="")
 price=db.Column(db.Integer,nullable=False); old_price=db.Column(db.Integer); stock=db.Column(db.Integer,default=0)
 image=db.Column(db.String(500),default=""); featured=db.Column(db.Boolean,default=False); active=db.Column(db.Boolean,default=True)
 created_at=db.Column(db.DateTime,default=datetime.utcnow)

class Order(db.Model):
 id=db.Column(db.Integer,primary_key=True); number=db.Column(db.String(24),unique=True,nullable=False)
 user_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False); customer=db.Column(db.String(120),nullable=False)
 phone=db.Column(db.String(30),nullable=False); province=db.Column(db.String(100),nullable=False); city=db.Column(db.String(100),nullable=False)
 address=db.Column(db.String(500),nullable=False); postal=db.Column(db.String(20),default=""); notes=db.Column(db.String(500),default="")
 subtotal=db.Column(db.Integer,nullable=False); shipping=db.Column(db.Integer,default=0); total=db.Column(db.Integer,nullable=False)
 payment=db.Column(db.String(30),default="cod"); payment_status=db.Column(db.String(30),default="unpaid")
 status=db.Column(db.String(30),default="pending"); created_at=db.Column(db.DateTime,default=datetime.utcnow)
 items=db.relationship("OrderItem",backref="order",cascade="all, delete-orphan")
class OrderItem(db.Model):
 id=db.Column(db.Integer,primary_key=True); order_id=db.Column(db.Integer,db.ForeignKey("order.id"),nullable=False)
 product_id=db.Column(db.Integer); name=db.Column(db.String(180),nullable=False); price=db.Column(db.Integer,nullable=False)
 qty=db.Column(db.Integer,nullable=False); image=db.Column(db.String(500),default="")

@login.user_loader
def load_user(uid): return db.session.get(User,int(uid))
def admin_only(fn):
 @wraps(fn)
 @login_required
 def inner(*a,**kw):
  if not current_user.is_admin: abort(403)
  return fn(*a,**kw)
 return inner
def money(v): return f"{int(v):,}".translate(str.maketrans("0123456789","۰۱۲۳۴۵۶۷۸۹"))
@app.context_processor
def globals():
 c=session.get("cart",{}); return dict(categories=CATS,statuses=STATUSES,cart_count=sum(int(v) for v in c.values()),money=money)
@app.template_filter("datefa")
def datefa(d): return d.strftime("%Y/%m/%d %H:%M") if d else "-"
def slugify(s): return re.sub(r"[^a-zA-Z0-9آ-ی]+","-",s).strip("-")[:140]+"-"+secrets.token_hex(3)
def cart_rows():
 c=session.get("cart",{}); ids=[]
 for k in c:
  try: ids.append(int(k))
  except: pass
 ps=Product.query.filter(Product.id.in_(ids),Product.active.is_(True)).all() if ids else []
 rows=[]; total=0
 for p in ps:
  q=max(1,min(int(c.get(str(p.id),1)),p.stock or 1,99)); rows.append({"p":p,"q":q,"line":p.price*q}); total+=p.price*q
 return rows,total

@app.route("/")
def home():
 q=request.args.get("q","").strip(); cat=request.args.get("category",""); sort=request.args.get("sort","featured")
 query=Product.query.filter_by(active=True)
 if q: query=query.filter(db.or_(Product.name.ilike(f"%{q}%"),Product.category.ilike(f"%{q}%"),Product.brand.ilike(f"%{q}%"),Product.models.ilike(f"%{q}%")))
 if cat in CATS: query=query.filter_by(category=cat)
 query=query.order_by(Product.price.asc() if sort=="low" else Product.price.desc() if sort=="high" else Product.created_at.desc() if sort=="new" else Product.featured.desc())
 return render_template("home.html",products=query.limit(80).all(),q=q,cat=cat,sort=sort)
@app.route("/p/<slug>")
def detail(slug):
 p=Product.query.filter_by(slug=slug,active=True).first_or_404()
 related=Product.query.filter(Product.active.is_(True),Product.category==p.category,Product.id!=p.id).limit(4).all()
 return render_template("detail.html",p=p,related=related)
@app.post("/cart/add/<int:pid>")
def add(pid):
 p=Product.query.filter_by(id=pid,active=True).first_or_404()
 if p.stock<1: flash("این محصول موجود نیست.","error")
 else:
  c=session.get("cart",{}); c[str(pid)]=min(int(c.get(str(pid),0))+max(1,int(request.form.get("qty",1) or 1)),p.stock,99); session["cart"]=c
  flash("محصول به سبد خرید اضافه شد.","success")
 return redirect(request.referrer or url_for("home"))
@app.route("/cart",methods=["GET","POST"])
def cart():
 if request.method=="POST":
  c=session.get("cart",{})
  for k in list(c):
   try:
    q=int(request.form.get("q_"+k,0)); p=db.session.get(Product,int(k))
    if q<=0 or not p or not p.active: c.pop(k,None)
    else: c[k]=min(q,p.stock,99)
   except: c.pop(k,None)
  session["cart"]=c; flash("سبد خرید به‌روز شد.","success"); return redirect(url_for("cart"))
 rows,total=cart_rows(); return render_template("cart.html",rows=rows,total=total)
@app.post("/cart/remove/<int:pid>")
def remove(pid):
 c=session.get("cart",{}); c.pop(str(pid),None); session["cart"]=c; return redirect(url_for("cart"))
@app.route("/register",methods=["GET","POST"])
def register():
 if current_user.is_authenticated: return redirect(url_for("home"))
 if request.method=="POST":
  name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower(); pw=request.form.get("password","")
  if len(name)<2 or "@" not in email or len(pw)<8: flash("نام، ایمیل معتبر و رمز حداقل ۸ کاراکتری وارد کنید.","error")
  elif User.query.filter_by(email=email).first(): flash("این ایمیل قبلاً ثبت شده است.","error")
  else:
   u=User(name=name,email=email); u.set_password(pw); db.session.add(u); db.session.commit(); login_user(u); return redirect(url_for("home"))
 return render_template("auth.html",mode="register")
@app.route("/login",methods=["GET","POST"])
def login():
 if request.method=="POST":
  u=User.query.filter_by(email=request.form.get("email","").strip().lower()).first()
  if u and u.check_password(request.form.get("password","")):
   login_user(u); return redirect(url_for("admin") if u.is_admin else url_for("home"))
  flash("ایمیل یا رمز عبور اشتباه است.","error")
 return render_template("auth.html",mode="login")
@app.post("/logout")
@login_required
def logout(): logout_user(); return redirect(url_for("home"))
@app.route("/checkout",methods=["GET","POST"])
@login_required
def checkout():
 rows,total=cart_rows()
 if not rows: flash("سبد خرید خالی است.","error"); return redirect(url_for("cart"))
 if request.method=="POST":
  fields={k:request.form.get(k,"").strip() for k in ["customer","phone","province","city","address","postal","notes"]}
  if not all(fields[k] for k in ["customer","phone","province","city","address"]): flash("فیلدهای ضروری را کامل کنید.","error")
  elif request.form.get("payment")!="cod": flash("پرداخت آنلاین تا اتصال درگاه رسمی فعال نیست؛ پرداخت هنگام تحویل را انتخاب کنید.","error")
  elif any(r["p"].stock<r["q"] for r in rows): flash("موجودی یکی از کالاها تغییر کرده؛ سبد را بررسی کنید.","error"); return redirect(url_for("cart"))
  else:
   ship=0 if total>=50000000 else 250000
   o=Order(number="DT-"+secrets.token_hex(4).upper(),user_id=current_user.id,customer=fields["customer"],phone=fields["phone"],province=fields["province"],city=fields["city"],address=fields["address"],postal=fields["postal"],notes=fields["notes"],subtotal=total,shipping=ship,total=total+ship,payment="cod")
   db.session.add(o); db.session.flush()
   for r in rows:
    p=r["p"]; db.session.add(OrderItem(order_id=o.id,product_id=p.id,name=p.name,price=p.price,qty=r["q"],image=p.image)); p.stock-=r["q"]
   db.session.commit(); session["cart"]={}; flash("سفارش با موفقیت ثبت شد.","success"); return redirect(url_for("order",number=o.number))
 return render_template("checkout.html",rows=rows,total=total)
@app.route("/orders")
@login_required
def orders(): return render_template("orders.html",orders=Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all())
@app.route("/order/<number>")
@login_required
def order(number):
 o=Order.query.filter_by(number=number).first_or_404()
 if o.user_id!=current_user.id and not current_user.is_admin: abort(403)
 return render_template("order.html",o=o)
@app.route("/admin")
@admin_only
def admin():
 return render_template("admin.html",products=Product.query.count(),orders=Order.query.count(),users=User.query.filter_by(is_admin=False).count(),pending=Order.query.filter_by(status="pending").count(),recent=Order.query.order_by(Order.created_at.desc()).limit(10).all())
@app.route("/admin/products")
@admin_only
def admin_products(): return render_template("admin_products.html",products=Product.query.order_by(Product.created_at.desc()).all())
@app.route("/admin/product",defaults={"pid":None},methods=["GET","POST"])
@app.route("/admin/product/<int:pid>",methods=["GET","POST"])
@admin_only
def product_edit(pid):
 p=db.session.get(Product,pid) if pid else Product()
 if pid and not p: abort(404)
 if request.method=="POST":
  try: price=int(request.form.get("price","0")); stock=int(request.form.get("stock","0")); old=int(request.form.get("old_price") or 0) or None
  except: flash("قیمت و موجودی باید عدد باشند.","error"); return render_template("product_form.html",p=p)
  name=request.form.get("name","").strip(); cat=request.form.get("category","")
  if not name or cat not in CATS or price<0 or stock<0: flash("اطلاعات محصول معتبر نیست.","error")
  else:
   p.name=name; p.category=cat; p.brand=request.form.get("brand","عمومی").strip(); p.models=request.form.get("models","").strip()
   p.description=request.form.get("description","").strip(); p.price=price; p.old_price=old; p.stock=stock
   p.image=request.form.get("image","").strip(); p.featured=bool(request.form.get("featured")); p.active=bool(request.form.get("active"))
   if not pid: p.slug=slugify(name); db.session.add(p)
   elif not p.slug: p.slug=slugify(name)
   db.session.commit(); flash("محصول ذخیره شد.","success"); return redirect(url_for("admin_products"))
 return render_template("product_form.html",p=p)
@app.post("/admin/product/<int:pid>/hide")
@admin_only
def hide_product(pid):
 p=db.session.get(Product,pid) or abort(404); p.active=False; db.session.commit(); flash("محصول از فروشگاه پنهان شد.","success"); return redirect(url_for("admin_products"))
@app.route("/admin/orders")
@admin_only
def admin_orders(): return render_template("admin_orders.html",orders=Order.query.order_by(Order.created_at.desc()).all())
@app.post("/admin/order/<int:oid>")
@admin_only
def set_status(oid):
 o=db.session.get(Order,oid) or abort(404); s=request.form.get("status")
 if s not in STATUSES: flash("وضعیت نامعتبر است.","error")
 elif o.status=="cancelled" and s!="cancelled": flash("سفارش لغوشده را از این مسیر دوباره فعال نکنید.","error")
 else:
  if s=="cancelled" and o.status!="cancelled":
   for it in o.items:
    p=db.session.get(Product,it.product_id) if it.product_id else None
    if p: p.stock+=it.qty
  o.status=s; db.session.commit(); flash("وضعیت سفارش به‌روزرسانی شد.","success")
 return redirect(url_for("admin_orders"))
@app.route("/health")
def health(): return {"status":"ok","store":"DIGITRUCK"}
@app.errorhandler(403)
def e403(e): return render_template("error.html",code=403,msg="اجازه دسترسی به این بخش را ندارید."),403
@app.errorhandler(404)
def e404(e): return render_template("error.html",code=404,msg="صفحه یا محصول پیدا نشد."),404

def seed():
 email=os.getenv("ADMIN_EMAIL","admin@digitruck.local").lower(); pw=os.getenv("ADMIN_PASSWORD","ChangeThisAdminPassword123!")
 if not User.query.filter_by(email=email).first():
  u=User(name="مدیر فروشگاه",email=email,is_admin=True); u.set_password(pw); db.session.add(u)
 if Product.query.count()==0:
  sample=[
  ("گارد سقف استیل ولوو FH","گارد و محافظ","ولوو",18500000,7,"https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?auto=format&fit=crop&w=800&q=80",1),
  ("زیرسپر استیل اسکانیا","زیرسپر و زیرپلاکی","اسکانیا",12900000,5,"https://images.unsplash.com/photo-1519003722824-194d4455a60c?auto=format&fit=crop&w=800&q=80",1),
  ("زیرپلاکی استیل طرح جدید","لوازم استیل","عمومی",2600000,18,"https://images.unsplash.com/photo-1504307651254-35680f356dfd?auto=format&fit=crop&w=800&q=80",1),
  ("چراغ جلو اسپرت ولوو","چراغ و روشنایی","ولوو",4850000,12,"https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?auto=format&fit=crop&w=800&q=80",0),
  ("جلوپنجره اسپرت اسکانیا","جلوپنجره و قاب","اسکانیا",19900000,4,"https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?auto=format&fit=crop&w=800&q=80",1),
  ("رینگ استیل ماشین سنگین","رینگ و لاستیک","عمومی",7700000,9,"https://images.unsplash.com/photo-1558618666-fcd25c85cd64?auto=format&fit=crop&w=800&q=80",0),
  ("چراغ سقفی LED","چراغ و روشنایی","عمومی",3200000,25,"https://images.unsplash.com/photo-1486262715619-67b85e0b08d3?auto=format&fit=crop&w=800&q=80",0),
  ("تجهیزات لوکس داخل کابین","تجهیزات داخل کابین","عمومی",5900000,10,"https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=800&q=80",0)]
  for n,c,b,pr,st,img,ft in sample: db.session.add(Product(name=n,slug=slugify(n),category=c,brand=b,models="ولوو، اسکانیا، بنز، MAN",description="مشخصات سازگاری و تصویر واقعی را پیش از فروش نهایی بررسی کنید.",price=pr,stock=st,image=img,featured=bool(ft)))
 db.session.commit()
with app.app_context(): db.create_all(); seed()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.getenv("PORT","5000")),debug=False)
