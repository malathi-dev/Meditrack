from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "meditrack.db")

app = Flask(__name__)

# ===============================
# DATABASE CONFIG
# ===============================
#DATABASE = "meditrack.db"

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ===============================
# INIT DATABASE
# ===============================
def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Medicines table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price REAL,
            stock INTEGER
        )
    """)

    # Bills table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Bill items table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bill_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER,
            medicine_id INTEGER,
            quantity INTEGER,
            price REAL,
            subtotal REAL,
            FOREIGN KEY(bill_id) REFERENCES bills(id),
            FOREIGN KEY(medicine_id) REFERENCES medicines(id)
        )
    """)

    # ✅ Customers table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE,
            email TEXT
        )
    """)

    conn.commit()
    conn.close()

def fix_bill_items_table():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(bill_items)")
    columns = [col["name"] for col in cur.fetchall()]

    if "price" not in columns:
        cur.execute("ALTER TABLE bill_items ADD COLUMN price REAL")

    if "subtotal" not in columns:
        cur.execute("ALTER TABLE bill_items ADD COLUMN subtotal REAL")

    conn.commit()
    conn.close()

def fix_bills_table():
    conn = get_db()
    cur = conn.cursor()

    # Check existing columns
    cur.execute("PRAGMA table_info(bills)")
    columns = [col["name"] for col in cur.fetchall()]

    if "status" not in columns:
        # Default status = 'pending' for new/existing bills
        cur.execute("ALTER TABLE bills ADD COLUMN status TEXT DEFAULT 'pending'")

    conn.commit()
    conn.close()
def fix_medicines_table():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(medicines)")
    columns = [col["name"] for col in cur.fetchall()]

    if "batch_no" not in columns:
        cur.execute("ALTER TABLE medicines ADD COLUMN batch_no TEXT")

    if "expiry_date" not in columns:
        cur.execute("ALTER TABLE medicines ADD COLUMN expiry_date DATE")

    conn.commit()
    conn.close()

def init_orderbook_tables():
    conn = get_db()
    cur = conn.cursor()

    # Distributors
    cur.execute("""
        CREATE TABLE IF NOT EXISTS distributors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT,
            address TEXT,
            gst_no TEXT
        )
    """)

    # Purchases
    cur.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            distributor_id INTEGER,
            invoice_no TEXT,
            txn_date DATE,
            total_amount REAL,
            adjusted_amount REAL DEFAULT 0,
            payable REAL,
            balance REAL,
            status TEXT DEFAULT 'pending',
            remarks TEXT,
            FOREIGN KEY(distributor_id) REFERENCES distributors(id)
        )
    """)

    # Payments
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            distributor_id INTEGER,
            txn_date DATE,
            amount REAL,
            method TEXT,
            FOREIGN KEY(distributor_id) REFERENCES distributors(id)
        )
    """)

    conn.commit()
    conn.close()

# ===============================
# INSERT SAMPLE DATA
# ===============================
def insert_sample_medicines():
    conn = get_db()
    cur = conn.cursor()

    medicines = [
        ("Paracetamol", 20, 100),
        ("Cetrizine", 15, 50),
        ("Amoxicillin", 120, 30),
        ("Vitamin C", 60, 80)
    ]

    for m in medicines:
        cur.execute("""
            INSERT OR IGNORE INTO medicines (name, price, stock)
            VALUES (?, ?, ?)
        """, m)

    conn.commit()
    conn.close()

# ===============================
# ROUTES
# ===============================

@app.route("/")
def dashboard():
    conn = get_db()
    cur = conn.cursor()

    # All medicines
    cur.execute("""
        SELECT id, name, batch_no, expiry_date, price, stock
        FROM medicines
        ORDER BY LOWER(name), batch_no
    """)
    medicines = cur.fetchall()

    # Low stock list
    cur.execute("SELECT * FROM medicines WHERE stock <= 10")
    low_stock = cur.fetchall()

    # Expiry alerts
    cur.execute("""
        SELECT name, batch_no, expiry_date, stock
        FROM medicines
        WHERE expiry_date IS NOT NULL
        AND DATE(expiry_date) <= DATE('now', '+30 days')
        ORDER BY expiry_date ASC
    """)
    expiry_alerts = cur.fetchall()

    # TOTAL SALES
    cur.execute("""
        SELECT SUM(total) AS total_sales
        FROM bills
        WHERE status='completed'
    """)
    total_sales = cur.fetchone()["total_sales"] or 0

    # TOTAL CUSTOMERS
    cur.execute("SELECT COUNT(*) AS total_customers FROM customers")
    total_customers = cur.fetchone()["total_customers"]

    # PENDING PAYMENTS
    cur.execute("""
        SELECT SUM(total) AS pending
        FROM bills
        WHERE status='pending'
    """)
    pending = cur.fetchone()["pending"] or 0

    # LOW STOCK COUNT
    cur.execute("SELECT COUNT(*) AS low_stock_count FROM medicines WHERE stock <= 10")
    low_stock_count = cur.fetchone()["low_stock_count"]

    conn.close()

    return render_template(
        "dashboard.html",
        medicines=medicines,
        low_stock=low_stock,
        expiry_alerts=expiry_alerts,
        total_sales=total_sales,
        total_customers=total_customers,
        pending=pending,
        low_stock_count=low_stock_count
    )

# =============================== BILLING ROUTE ===============================
from datetime import date

@app.route("/billing", methods=["GET", "POST"])
def billing():
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # =========================
    # GET OR CREATE ACTIVE BILL
    # =========================
    cur.execute("""
        SELECT id FROM bills
        WHERE status='pending'
        ORDER BY id DESC
        LIMIT 1
    """)
    bill = cur.fetchone()

    if bill:
        bill_id = bill["id"]
    else:
        cur.execute("INSERT INTO bills (total, status) VALUES (0,'pending')")
        conn.commit()
        bill_id = cur.lastrowid

    # =========================
    # ADD MEDICINE TO BILL
    # =========================
    if request.method == "POST":
        medicine_id = int(request.form["medicine_id"])
        quantity = int(request.form.get("quantity", 1))

        cur.execute("SELECT * FROM medicines WHERE id=?", (medicine_id,))
        medicine = cur.fetchone()

        if not medicine:
            conn.close()
            return redirect(url_for("billing"))

        # Expiry check
        if medicine["expiry_date"]:
            expiry_date = date.fromisoformat(medicine["expiry_date"])
            if expiry_date < date.today():
                conn.close()
                return redirect(url_for("billing", expired=1))

        # Stock check
        if medicine["stock"] < quantity:
            conn.close()
            return redirect(url_for("billing", nostock=1))

        # Check existing item
        cur.execute("""
            SELECT id, quantity FROM bill_items
            WHERE bill_id=? AND medicine_id=?
        """, (bill_id, medicine_id))

        existing_item = cur.fetchone()

        if existing_item:
            new_qty = existing_item["quantity"] + quantity
            new_subtotal = new_qty * medicine["price"]

            cur.execute("""
                UPDATE bill_items
                SET quantity=?, subtotal=?
                WHERE id=?
            """, (new_qty, new_subtotal, existing_item["id"]))

        else:
            subtotal = medicine["price"] * quantity

            cur.execute("""
                INSERT INTO bill_items (bill_id, medicine_id, quantity, price, subtotal)
                VALUES (?, ?, ?, ?, ?)
            """, (bill_id, medicine_id, quantity, medicine["price"], subtotal))

        # Reduce stock
        cur.execute("""
            UPDATE medicines
            SET stock = stock - ?
            WHERE id=?
        """, (quantity, medicine_id))

        conn.commit()
        return redirect(url_for("billing"))

    # =========================
    # FETCH MEDICINES
    # =========================
    cur.execute("SELECT * FROM medicines ORDER BY name ASC")
    medicines = cur.fetchall()

    # =========================
    # FETCH BILL ITEMS
    # =========================
    cur.execute("""
        SELECT bi.id, m.name, m.batch_no, m.expiry_date,
               bi.quantity, bi.price, bi.subtotal
        FROM bill_items bi
        JOIN medicines m ON bi.medicine_id = m.id
        WHERE bi.bill_id = ?
    """, (bill_id,))
    items = cur.fetchall()

    # =========================
    # TOTAL CALCULATION
    # =========================
    subtotal = sum(i["subtotal"] for i in items)
    gst = round(subtotal * 0.0, 2)      # change later if needed
    discount = 0
    grand_total = subtotal + gst - discount

    cur.execute("UPDATE bills SET total=? WHERE id=?", (grand_total, bill_id))
    conn.commit()
    conn.close()

    # =========================
    # RENDER PAGE
    # =========================
    return render_template(
        "billing.html",
        medicines=medicines,
        items=items,
        subtotal=subtotal,
        gst=gst,
        discount=discount,
        grand_total=grand_total,
        bill_id=bill_id,
        expired=request.args.get("expired"),
        nostock=request.args.get("nostock"),
        today=date.today().isoformat()
    )

# =============================== ADD NEW MEDICINE ===============================
@app.route("/add_medicine", methods=["POST"])
def add_medicine():
    name = request.form["name"]
    company = request.form.get("company")
    batch_no = request.form.get("batch_no") or None
    expiry_date = request.form.get("expiry_date") or None
    price = float(request.form["price"])
    stock = int(request.form["stock"])

    conn = get_db()
    cur = conn.cursor()

    # Check existing same batch
    cur.execute("""
        SELECT id, stock FROM medicines
        WHERE LOWER(name)=LOWER(?)
        AND company=?
        AND price=?
        AND (batch_no IS ? OR batch_no=?)
        AND (expiry_date IS ? OR expiry_date=?)
    """, (name, company, price, batch_no, batch_no, expiry_date, expiry_date))

    existing = cur.fetchone()

    if existing:
        new_stock = existing["stock"] + stock
        cur.execute(
            "UPDATE medicines SET stock=? WHERE id=?",
            (new_stock, existing["id"])
        )
    else:
        cur.execute("""
            INSERT INTO medicines
            (name, company, batch_no, expiry_date, price, stock)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, company,batch_no, expiry_date, price, stock))

    conn.commit()
    conn.close()

    return redirect(url_for("inventory"))
# =============================== REMOVE ITEM FROM BILL ===============================
@app.route("/remove-from-bill/<int:item_id>", methods=["POST"])
def remove_from_bill(item_id):
    conn = get_db()
    cur = conn.cursor()

    # Restore stock
    cur.execute("SELECT medicine_id, quantity FROM bill_items WHERE id=?", (item_id,))
    item = cur.fetchone()
    if item:
        cur.execute("UPDATE medicines SET stock = stock + ? WHERE id=?", (item["quantity"], item["medicine_id"]))
        cur.execute("DELETE FROM bill_items WHERE id=?", (item_id,))
        conn.commit()

    conn.close()
    return redirect(url_for("billing"))
# ===============================
# Check out print the bill 
# ===============================

@app.route("/checkout/<int:bill_id>")
def checkout(bill_id):
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT m.name, bi.quantity, bi.price, bi.subtotal
        FROM bill_items bi
        JOIN medicines m ON bi.medicine_id = m.id
        WHERE bi.bill_id=?
    """, (bill_id,))
    items = cur.fetchall()

    grand_total = sum(i["subtotal"] for i in items)

    cur.execute("UPDATE bills SET status='completed' WHERE id=?", (bill_id,))
    conn.commit()
    conn.close()

    return render_template("checkout.html",
                           items=items,
                           grand_total=grand_total)

# =============================== INVENTORY ===============================
from datetime import date

@app.route("/inventory")
def inventory():
    conn = get_db()
    cur = conn.cursor()

    # Fetch all medicines
    cur.execute("SELECT * FROM medicines ORDER BY LOWER(name), batch_no")
    medicines = cur.fetchall()

    # Low stock items (<=10)
    cur.execute("SELECT * FROM medicines WHERE stock <= 10 ORDER BY stock ASC")
    low_stock = cur.fetchall()

    # Expiry alerts (next 30 days)
    cur.execute("""
        SELECT * FROM medicines
        WHERE expiry_date IS NOT NULL
        AND DATE(expiry_date) <= DATE('now', '+30 days')
        ORDER BY expiry_date ASC
    """)
    expiry_alerts = cur.fetchall()

    # Calculate total stock value
    total_value = sum(m["price"] * m["stock"] for m in medicines)
    total_products = len(medicines)
    cur = get_db().cursor()
    cur.execute("SELECT * FROM medicines WHERE DATE(expiry_date) < DATE('now')")
    expired_batches = cur.fetchall()

    conn.close()

    return render_template(
        "inventory.html",
        medicines=medicines,
        low_stock=low_stock,
        expiry_alerts=expiry_alerts,
        total_value=total_value,
            total_products=total_products,
           expired_batches=expired_batches,
            today=str(date.today())
    )


# =============================== purchase ===============================
@app.route("/purchase", methods=["GET", "POST"])
def purchase():
    conn = sqlite3.connect("meditrack.db")
    cursor = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name")
        price = request.form.get("price")
        stock = request.form.get("stock")
        batch_no = request.form.get("batch_no")
        expiry_date = request.form.get("expiry_date")

        cursor.execute("""
            INSERT INTO medicines (name, price, stock, batch_no, expiry_date)
            VALUES (?, ?, ?, ?, ?)
        """, (name, price, stock, batch_no, expiry_date))

        conn.commit()

    conn.close()
    return render_template("purchase.html")


# ===================EDIT MEDICINE===============================
@app.route("/edit_medicine/<int:med_id>", methods=["GET", "POST"])
def edit_medicine(med_id):
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form["name"]
        company = request.form.get("company")
        batch_no = request.form.get("batch_no")
        expiry_date = request.form.get("expiry_date")
        price = request.form["price"]
        stock = request.form["stock"]

        cur.execute("""
            UPDATE medicines
            SET name=?, company=?, batch_no=?, expiry_date=?, price=?, stock=?
            WHERE id=?
        """, (name, company, batch_no, expiry_date, price, stock, med_id))

        conn.commit()
        conn.close()
        return redirect(url_for("inventory"))

    cur.execute("SELECT * FROM medicines WHERE id=?", (med_id,))
    medicine = cur.fetchone()
    conn.close()

    return render_template("edit_medicine.html", medicine=medicine)
#===================== DELETE MEDICINE================================
@app.route("/delete-medicine/<int:med_id>", methods=["POST"])
def delete_medicine(med_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM medicines WHERE id=?", (med_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("inventory"))
# ===============================
# CUSTOMERS PAGE
# ===============================
@app.route("/customers")
def customers():
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM customers ORDER BY name ASC")
    rows = cur.fetchall()

    customers = []
    total_credit = 0

    for r in rows:
        credit_balance = r["credit_balance"] if "credit_balance" in r.keys() else 0
        total_purchases = r["total_purchases"] if "total_purchases" in r.keys() else 0
        last_visit = r["last_visit"] if "last_visit" in r.keys() else "-"
        address = r["address"] if "address" in r.keys() else ""
        email = r["email"] if "email" in r.keys() else ""

        total_credit += credit_balance if credit_balance else 0

        customers.append({
            "id": r["id"],
            "name": r["name"],
            "phone": r["phone"],
            "email": email,
            "address": address,
            "credit_balance": credit_balance,
            "total_purchases": total_purchases,
            "last_visit": last_visit
        })

    conn.close()

    return render_template(
        "customers.html",
        customers=customers,
        total_credit=total_credit
    )


@app.route("/add_customer", methods=["POST"])
def add_customer():
    name = request.form["name"]
    phone = request.form["phone"]
    email = request.form.get("email", "")
    address = request.form.get("address", "")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO customers
        (name, phone, email, address, credit_balance, total_purchases, last_visit)
        VALUES (?, ?, ?, ?, 0, 0, DATE('now'))
    """, (name, phone, email, address))

    conn.commit()
    conn.close()

    return redirect(url_for("customers"))


@app.route("/edit_customer/<int:id>", methods=["GET", "POST"])
def edit_customer(id):
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get customer
    cur.execute("SELECT * FROM customers WHERE id=?", (id,))
    customer = cur.fetchone()

    if not customer:
        conn.close()
        return redirect(url_for("customers"))

    # Update customer
    if request.method == "POST":
        name = request.form["name"]
        contact = request.form["contact"]
        credit_balance = request.form["credit_balance"]
        total_purchases = request.form["total_purchases"]
        last_visit = request.form["last_visit"]

        cur.execute("""
            UPDATE customers
            SET name=?, contact=?, credit_balance=?, total_purchases=?, last_visit=?
            WHERE id=?
        """, (name, contact, credit_balance, total_purchases, last_visit, id))

        conn.commit()
        conn.close()
        return redirect(url_for("customers"))

    conn.close()
    return render_template("edit_customer.html", customer=customer)


@app.route("/delete-customer/<int:cust_id>", methods=["POST"])
def delete_customer(cust_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM customers WHERE id=?", (cust_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("customers"))
# =============================== REPORTS ===============================
@app.route("/reports")
def reports():
    conn = get_db()
    cur = conn.cursor()

    # Total customers
    cur.execute("SELECT COUNT(*) AS total_customers FROM customers")
    total_customers = cur.fetchone()["total_customers"]

    # Total sales (completed bills only)
    cur.execute("""
        SELECT SUM(total) AS total_sales
        FROM bills
        WHERE status='completed'
    """)
    total_sales = cur.fetchone()["total_sales"] or 0
    
        

    # Pending amount
    cur.execute("""
        SELECT SUM(total) AS pending
        FROM bills
        WHERE status='pending'
    """)
    pending = cur.fetchone()["pending"] or 0

    conn.close()

    return render_template(
        "reports.html",
        total_customers=total_customers,
        total_sales=total_sales,
        pending=pending
    )
@app.route("/adjust_stock/<int:med_id>", methods=["POST"])
def adjust_stock(med_id):
    qty = int(request.form["quantity"])

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "UPDATE medicines SET stock = stock + ? WHERE id=?",
        (qty, med_id)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("inventory"))
#============================== ORDER BOOK ===============================
@app.route("/orderbook")
def orderbook():
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # =========================
    # FETCH DISTRIBUTORS
    # =========================
    cur.execute("SELECT * FROM distributors ORDER BY name ASC")
    distributors = cur.fetchall()

    dist_list = []

    for d in distributors:
        dist_id = d["id"]

        # =========================
        # TOTAL PURCHASES
        # =========================
        cur.execute("""
            SELECT SUM(total_amount) AS total 
            FROM purchases 
            WHERE distributor_id=?
        """, (dist_id,))
        total_purchase = cur.fetchone()["total"] or 0

        # =========================
        # TOTAL PAYMENTS
        # =========================
        cur.execute("""
            SELECT SUM(amount) AS total_pay 
            FROM payments 
            WHERE distributor_id=?
        """, (dist_id,))
        total_pay = cur.fetchone()["total_pay"] or 0

        # =========================
        # BALANCE
        # =========================
        balance = total_purchase - total_pay

        dist_list.append({
            "id": dist_id,
            "name": d["name"],
            "contact": d["contact"],
            "address": d["address"],
            "gst_no": d["gst_no"],
            "total_purchase": total_purchase,
            "payments": total_pay,
            "balance": balance
        })

    # =========================
    # STATS (FOR CARDS UI)
    # =========================
    shortbook_count = 0   # later we can calculate from stock

    conn.close()

    return render_template(
        "orderbook.html",
        distributors=dist_list,   # IMPORTANT: keep your processed data
        shortbook_count=shortbook_count
    )

# =============================== ADD DISTRIBUTOR ===============================
@app.route("/add_distributor", methods=["GET", "POST"])
def add_distributor():
    if request.method == "POST":
        name = request.form["name"]
        contact = request.form.get("contact", "")
        address = request.form.get("address", "")
        gst_no = request.form.get("gst_no", "")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO distributors (name, contact, address, gst_no)
            VALUES (?, ?, ?, ?)
        """, (name, contact, address, gst_no))
        conn.commit()
        conn.close()
        return redirect(url_for("orderbook"))

    return render_template("add_distributor.html")

# =============================== EDIT DISTRIBUTOR ===============================
@app.route("/edit_distributor/<int:dist_id>", methods=["GET", "POST"])
def edit_distributor(dist_id):
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Fetch distributor
    cur.execute("SELECT * FROM distributors WHERE id=?", (dist_id,))
    distributor = cur.fetchone()

    if not distributor:
        conn.close()
        return redirect(url_for("orderbook"))

    if request.method == "POST":
        name = request.form["name"]
        contact = request.form.get("contact", "")
        address = request.form.get("address", "")
        gst_no = request.form.get("gst_no", "")

        cur.execute("""
            UPDATE distributors
            SET name=?, contact=?, address=?, gst_no=?
            WHERE id=?
        """, (name, contact, address, gst_no, dist_id))
        conn.commit()
        conn.close()
        return redirect(url_for("orderbook"))

    conn.close()
    return render_template("edit_distributor.html", distributor=distributor)

# =============================== DELETE DISTRIBUTOR ===============================
@app.route("/delete_distributor/<int:dist_id>", methods=["POST"])
def delete_distributor(dist_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM distributors WHERE id=?", (dist_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("orderbook"))

# =============================== ADD PURCHASE ===============================
@app.route("/add_purchase", methods=["GET", "POST"])
def add_purchase():
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Fetch all distributors for selection
    cur.execute("SELECT * FROM distributors ORDER BY name ASC")
    distributors = cur.fetchall()

    if request.method == "POST":
        distributor_id = int(request.form["distributor_id"])
        invoice_no = request.form["invoice_no"]
        txn_date = request.form["txn_date"]  # format YYYY-MM-DD
        total_amount = float(request.form["total_amount"])
        remarks = request.form.get("remarks", "")
        payable = total_amount  # initial payable
        balance = total_amount  # initial balance

        cur.execute("""
            INSERT INTO purchases
            (distributor_id, invoice_no, txn_date, total_amount, adjusted_amount, payable, balance, remarks)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?)
        """, (distributor_id, invoice_no, txn_date, total_amount, payable, balance, remarks))

        conn.commit()
        conn.close()
        return redirect(url_for("orderbook"))

    conn.close()
    return render_template("add_purchase.html", distributors=distributors)
# =============================== ADD PAYMENT ===============================
@app.route("/add_payment", methods=["GET", "POST"])
def add_payment():
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Fetch all distributors for selection
    cur.execute("SELECT * FROM distributors ORDER BY name ASC")
    distributors = cur.fetchall()

    if request.method == "POST":
        distributor_id = int(request.form["distributor_id"])
        txn_date = request.form["txn_date"]  # format YYYY-MM-DD
        amount = float(request.form["amount"])
        method = request.form.get("method", "Cash")

        cur.execute("""
            INSERT INTO payments
            (distributor_id, txn_date, amount, method)
            VALUES (?, ?, ?, ?)
        """, (distributor_id, txn_date, amount, method))

        # Update balance in purchases table
        cur.execute("""
            SELECT SUM(total_amount) AS total_purchase, SUM(adjusted_amount) AS total_paid
            FROM purchases WHERE distributor_id=?
        """, (distributor_id,))
        result = cur.fetchone()
        total_purchase = result["total_purchase"] or 0
        total_paid = (result["total_paid"] or 0) + amount
        new_balance = total_purchase - total_paid

        cur.execute("""
            UPDATE purchases SET adjusted_amount=?
            WHERE distributor_id=?
        """, (total_paid, distributor_id))

        conn.commit()
        conn.close()
        return redirect(url_for("orderbook"))

    conn.close()
    return render_template("add_payment.html", distributors=distributors)


# ===============================
# APP START
# ===============================
if __name__ == "__main__":
    init_db()
    fix_bill_items_table()
    fix_bills_table()
    fix_medicines_table()
    init_orderbook_tables()   
    #insert_sample_medicines()
    app.run(debug=True)


