import os
from time import time
from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd, dtFormat

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd
app.jinja_env.filters["dtFormat"] = dtFormat

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    wallets = db.execute("SELECT * FROM wallet WHERE user_id = :user_id AND amount > 0", user_id=session.get("user_id"))
    stocks = []
    total = 0
    for wallet in wallets:
        stockData = lookup(wallet["symbol"])
        stocks.append(
            {
                "symbol": wallet["symbol"],
                "name": stockData["name"],
                "amount": wallet["amount"],
                "price": stockData["price"],
                "total": float(stockData["price"]) * float(wallet["amount"])
            }
        )
        total += float(stockData["price"]) * float(wallet["amount"])
    cash = float(
        db.execute(
            "SELECT cash FROM users WHERE id = :user_id",
            user_id=session.get("user_id")
        )[0]["cash"]
    )
    print(total)
    print(cash)
    balance = total + cash
    print(balance)
    
    return render_template("index.html", stocks=stocks, cash=cash, total=total, balance=balance)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol") or not request.form.get("shares"):
            return apology("must provide a symbol and a share amount")
        if int(request.form.get("shares")) < 1:
            return apology("amount must be positive integer", 403)
        stockData = lookup(request.form.get("symbol"))
        if not stockData:
            return apology("symbol not found", 404)
        total = stockData["price"] * int(request.form.get("shares"))
        balance = db.execute("SELECT cash FROM users WHERE id = :id", id=session.get("user_id"))
        balance = int(balance[0]['cash'])
        if total > balance:
            return apology("balance not enough", 403)
        db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash=balance-total, id=session.get("user_id"))
        db.execute(
            """INSERT INTO wallet (
                user_id,
                symbol,
                amount
            ) VALUES (
                :userId,
                :symbol,
                :amount
            ) ON CONFLICT(symbol) DO
                UPDATE SET amount = amount+:amount
            """,
            userId=session.get("user_id"),
            symbol=request.form.get("symbol").upper(),
            amount=request.form.get("shares")
        )
        db.execute(
            """INSERT INTO history (
                user_id,
                symbol,
                value,
                amount,
                date
            ) VALUES (
                :userId,
                :symbol,
                :value,
                :amount,
                :date
            )
            """,
            userId=session.get("user_id"),
            symbol=request.form.get("symbol").upper(),
            value=stockData["price"],
            amount=request.form.get("shares"),
            date=int(time()*1000)
        )
        flash("Bought!")
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT * FROM history WHERE user_id = :user_id", user_id=session.get("user_id"))
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        flash("Welcome!")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    """Change user password"""

    user = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session.get("user_id"))
    print(user)
    if request.method == "POST":
        # Ensure old password was submitted
        if not request.form.get("old"):
            return apology("must enter old password", 403)
        
        # Ensure old password is correct
        if not check_password_hash(user[0]["hash"], request.form.get("old")):
          return apology("incorrect password", 403)

        # Ensure new password was submitted
        elif not request.form.get("new"):
            return apology("must enter new password", 403)

        # Ensure confirmation was submitted and equals password
        elif request.form.get("new") != request.form.get("confirmation"):
            return apology("new password and confirmation doesn't match", 403)

        # update password
        db.execute(
          "UPDATE users set hash = :hash",
          hash=generate_password_hash(request.form.get("new"))
        )
        flash("Password changed!")
        return redirect("/")
      

    else:
      return render_template("change_password.html", user=user[0]["username"])

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        if not request.form.get("symbol"):
            print("Quote symbol " + request.form.get("symbol"))
            return apology("must provide a ticker symbol", 403)
        stockData = lookup(request.form.get("symbol").upper())
        if not stockData:
            return apology("symbol not found", 404)
        return render_template("quoted.html", data=stockData)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Check if the user exists already
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        if len(rows) != 0:
            return apology("this username is not available", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure confirmation was submitted and equals password
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("password and confirmation doesn't match", 403)

        # Create the user
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
            username=request.form.get("username"), hash=generate_password_hash(request.form.get("password")))

        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol") or not request.form.get("shares"):
            return apology("Bad request", 403)
        if int(request.form.get("shares")) < 1:
            return apology("Must provide an amount greater than 0", 403)
        stocks = db.execute(
            "SELECT * FROM wallet WHERE user_id = :user_id AND symbol = :symbol",
            user_id=session.get("user_id"),
            symbol=request.form.get("symbol").upper()
        )
        if len(stocks) < 1:
            return apology("This symbol does not exist in wallet", 403)
        if int(request.form.get("shares")) > int(stocks[0]["amount"]):
            return apology("Wallet doesn't have this amount of shares", 403)
        stockData = lookup(request.form.get("symbol"))
        db.execute(
            "UPDATE users SET cash = cash+:cash WHERE id = :user_id",
            cash=float(stockData["price"]) * int(request.form.get("shares")),
            user_id=session.get("user_id")
        )
        db.execute(
          "UPDATE wallet SET amount = amount - :amount WHERE user_id = :user_id AND symbol = :symbol",
          amount=request.form.get("shares"),
          user_id=session.get("user_id"),
          symbol=request.form.get("symbol").upper()
        )
        db.execute(
            """INSERT INTO history (
                user_id,
                symbol,
                value,
                amount,
                date
            ) VALUES (
                :userId,
                :symbol,
                :value,
                :amount,
                :date
            )
            """,
            userId=session.get("user_id"),
            symbol=request.form.get("symbol").upper(),
            value=stockData["price"],
            amount=-int(request.form.get("shares")),
            date=int(time()*1000)
        )
        flash("Sold!")
        return redirect("/")

    else:
        stocks = db.execute(
            "SELECT * FROM wallet WHERE user_id = :user_id",
            user_id=session.get("user_id"),
        )
        return render_template("sell.html", stocks=stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
