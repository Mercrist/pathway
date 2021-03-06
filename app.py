from flask import Flask, flash, redirect, url_for, render_template, request, session
from bson.objectid import ObjectId
from datetime import datetime
import bcrypt
import model
import re

app = Flask(__name__)
app.config.from_object('config')
mongo = model.PyMongoFixed(app)
db = mongo.db
for collection in model.collections:
    if collection not in db.list_collection_names():
        db.create_collection(collection)
        if collection == "companies":
            with app.app_context():
                model.reset_comp_collection()

        if collection == "reviews":
            with app.app_context():
                model.reset_review_collection()

@app.route("/")
@app.route("/index")
def index():
    """Route for index page. Renders 'index.html' file. Currently has
    placeholder data for debugging/visualization of work.
    """
    if db.reviews.count_documents({}) == 0:
        reviews = None
    else:
        # '.limit()' limits the amount of documents queried
        reviews = db.reviews.find().sort('date_posted', -1).limit(5)
    # -1 sorts in descending order
    companies = db.companies.find().sort("company_rat", -1).limit(4)
    if 'username' in session:
        user = db.users.find_one({'username':session['username']})
    else:
        user = None
    return render_template("index.html", recent_reviews=reviews, companies=companies, to_comp_obj=model.to_company_obj,
                            user=user)


@app.route('/signup')
def signup():
    """Endpoint for 'signup.html'
    """
    if 'username' in session:
        user = db.users.find_one({'username':session['username']})
    else:
        user = None
    return render_template('signup.html',user=user)


@app.route("/user", methods=['GET', 'POST'])
@app.route("/user/<username>", methods=['GET', 'POST'])
def user():
    """Route for user's profile page with information and account controls.
    If the user is not logged in, redirect to current page with a warning.
    """
    if 'username' not in session:
        return redirect(url_for("login"))

    users = db.users
    reviews = db.reviews
    user = users.find_one({"username": session["username"]})
    user_reviews = [rev for rev in reviews.find({"user":user['username']})]
    formattted_date = datetime.strftime(user['creation_time'],  '%m-%d-%Y')
    return render_template('user.html', user=user, creation_day=formattted_date, reviews=user_reviews)

@app.route("/change_password/<username>", methods=["POST"])
def change_password(username):
    form = request.form
    users = db.users
    if session['username']:
        #user is valid
        user = {"username": username}
        salt = bcrypt.gensalt()
        new_pw = {
            "$set": {"password": bcrypt.hashpw(form['newPassword'].encode('utf-8'),salt)}
        }
        users.update_one(user, new_pw)
        flash("Password updated!", "success")

    else:
        flash("Invalid user!", "danger")

    return redirect(url_for("user"))

@app.route("/change_pfp/<username>", methods=['POST'])
def change_pfp(username):
    users = db.users
    if session['username']:
        pf = request.files['profile_image']
        filename = model.hash_profile_name(pf.filename)
        mongo.save_file(filename,pf)
        user = {"username":username}
        new_pf = {
            "$set" : {"profile_pic":filename}
        }
        users.update_one(user, new_pf)
        flash("Succesfully changed profile picture!", "success")
        return redirect(url_for("user"))
    else:
        flash("Invalid user!", "danger")
    return redirect(url_for("user"))

@app.route('/company-admin', methods=['GET', 'POST'])
def company_admin():
    # in case anyone resets all of the companies
    if db.companies.count_documents({}) == 0:
        model.reset_comp_collection()

    if request.method == 'POST':
        # remove companies
        if 'remove_comp_button' in request.form and request.form['remove_comp_button'] == "clicked":
            to_remove = request.form['comp_remove']
            if not db.companies.find_one_and_delete({'name': to_remove}):
                flash(f"{to_remove} doesn't exist!", "danger")

            else:
                flash(f"{to_remove} was removed from the database!", "success")

    if 'username' in session:
        user = db.users.find_one({'username':session['username']})
    else:
        user = None

    return render_template("company-admin.html", categories=model.company_categories,user=user)

@app.route('/companies/')
def companies():
    # displays the top 10 highest rated companies
    comps = db.companies.find().sort("company_rat", -1).limit(10)
    if 'username' in session:
        user = db.users.find_one({'username':session['username']})
    else:
        user = None
    return render_template("companies.html", companies=comps, to_comp_obj=model.to_company_obj,user=user)

@app.route('/companies/<company_name>')
def company_page(company_name):
    comp = db.companies.find_one({"name_lower": company_name})

    if not comp:
        flash("Accessed an invalid URL.", "danger")
        return redirect(url_for('companies'))

    if db.reviews.count_documents({'company.name': comp['name']}) == 0:
        reviews = None

    else:
        reviews = [rev for rev in db.reviews.find({'company.name': comp['name']}).sort('date_posted', -1).limit(8)]

    if 'username' in session:
        user = db.users.find_one({'username':session['username']})
    else:
        user = None
    return render_template('company.html', company=model.to_company_obj(comp),
                            reviews=reviews, user=user)

@app.route('/search')
def search():
    query = request.args['search-field']
    # won't allow special characters like * and \ which crash the regex
    # all alphanumeric sequences that could contain ' and . and some other punctuation characters
    valid_pattern = re.compile("^[a-zA-Z0-9.'&]+$")
    is_valid = valid_pattern.findall(query)

    # not a valid pattern or . (queries everything in the db)
    if not is_valid or query == ".":
        num_queries = 0
        res = None

    else:
        # all companies that have the search query in the name
        # options i makes the search case insensitive
        res = db.companies.find({'name': {'$regex': query, '$options': 'i'}})
        # doesn't consume the cursor, checks for no valid results
        num_queries = len(list(res.clone()))

    if 'username' in session:
        user = db.users.find_one({'username':session['username']})
    else:
        user = None
    return render_template("search.html", results=res, num_queries=num_queries,
                            query=query, to_comp_obj=model.to_company_obj, user=user)

@app.route('/file/<path:filename>')
def file(filename):
    """Helper route for getting files from database. Functions as wrapper for
    mongo.send_file function.

    Args:
        filename (str): file to return
    """
    return mongo.send_file(filename)

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method == "POST":
        users = db.users
        login_user = users.find_one({'username':request.form['username']})
        if login_user:
            db_password = login_user['password']
            password = request.form['password'].encode('utf-8')
            if bcrypt.checkpw(password,db_password):
                session['username'] = request.form['username']
                return redirect(url_for('index'))
            else:
                flash('Invalid username/password combination.', 'danger')
        else:
            flash('User not found.', 'danger')

    if 'username' in session:
        user = db.users.find_one({'username':session['username']})
    else:
        user = None
    return render_template('login.html', user=user)

@app.route('/logout')
def logout():
    """Logging out endpoint. Clears all local
    session information and redirects to index.
    """
    session.clear()
    return redirect('/')

@app.route('/create_user', methods=['POST'])
def create_user():
    """Helper route for creating users.Takes in form information and
    pushes user to database. Should only be accessed from signup route.

    Args:
        Form:
            username (str)
            password (str)
            email (str)
            profile_pic (file)
    """
    users = db.users
    existing_user = users.find_one({'username': request.form['username']})
    existing_email = users.find_one({'email': request.form['email']})

    if not existing_user and not existing_email:
        if not request.files.get('profile_image', None):
            # default pfp
            user = model.User(
                request.form['username'],
                pswd=request.form['password'],
                email=request.form['email'].strip()
            )

        else:
            pf = request.files['profile_image']
            filename = model.hash_profile_name(pf.filename)
            user = model.User(
                request.form['username'],
                pswd=request.form['password'],
                email=request.form['email'].strip(),
                profile_pic=filename
            )
            mongo.save_file(filename, pf)

        users.insert_one(user.to_json())
        session['username'] = user.username

    elif existing_user:
        flash("Already an existing user.", "danger")
        return redirect(url_for('signup'))

    else:
        flash("Email already in use.", "danger")
        return redirect(url_for('signup'))

    return redirect(url_for('index'))


@app.route('/company-admin/created', methods=['POST'])
def create_company():
    if 'add_comp_button' in request.form and request.form['add_comp_button'] == "clicked":
        comp_name = request.form['comp_name']
        if db.companies.find_one({"name": comp_name}):
            flash(f"{comp_name} already exists!", "danger")

        else:
            # save company logo image
            logo_img = request.files['comp_logo_img']
            logo_filename = model.hash_profile_name(logo_img.filename)
            mongo.save_file(logo_filename, logo_img)

            # banner was not selected
            # empty FileStorage objects evaluate as False
            if not request.files.get('comp_banner_img', None):
                # default banner img
                banner_filename = "../static/Images/Backup/default-banner.jpg"

            else:
                banner_img = request.files['comp_banner_img']
                banner_filename = model.hash_profile_name(banner_img.filename)
                mongo.save_file(banner_filename, banner_img)

            # initialize all the hidden company attributes
            new_comp = model.Company(comp_name, request.form['comp_category'], logo_filename,
                                request.form['comp_description'], banner_filename)

            db.companies.insert_one(new_comp.to_json())
            flash(f"{new_comp.name} was added to the list of companies!", "success")

    return redirect(url_for('company_admin'))

@app.route("/reviews", methods=["GET"])
def reviews():
    rev = db.reviews.find().sort('date_posted', -1).limit(10)
    if 'username' in session:
        user = db.users.find_one({'username':session['username']})
    else:
        user = None
    return render_template("reviews.html",reviews=rev,user=user)

@app.route("/reviews/<review_id>")
def view_review(review_id):
    try:
        review = db.reviews.find_one({"_id":ObjectId(review_id)})

    except:
        flash("Invalid URL accessed!", "danger")
        return redirect(url_for('reviews'))

    if not review:
        #NOTE: should redirect with flag to indicate non-existing review
        flash("Review not found!",'danger')
        return redirect(url_for("reviews"))
    if 'username' in session:
        user = db.users.find_one({'username':session['username']})
    else:
        user = None

    formattted_date = datetime.strftime(review['date_posted'],  '%m-%d-%Y')
    return render_template("view_review.html", creation_date=formattted_date, review=review, user=user)

@app.route('/reviews/submit/', defaults={'company_to_review': None}, methods=['GET', 'POST'])
@app.route("/reviews/submit/<company_to_review>/", methods=["GET","POST"])
def submit_review(company_to_review):
    if 'username' not in session:
        flash('Cannnot write a review without being signed in!', 'danger')
        # returns the current page
        return redirect(request.referrer)

    if request.method == "POST":
        form = request.form

        comp = db.companies.find_one({'name':form['company']})

        if not comp:
            flash(f"{form['company']} doesn't exist!", "danger")

        else:
            if form['location'] == 'N/A':
                location = ("None", "Remote")

            else:
                location = tuple((form['city'],form['location']))

            # optional review fields
            if 'workRatingOptions' in form:
                workRat = int(form['workRatingOptions'])

            else:
                workRat = None

            if 'cultureRatingOptions' in form:
                cultRat = int(form['cultureRatingOptions'])

            else:
                cultRat = None

            if 'interviewRatingOptions' in form:
                intRat = int(form['interviewRatingOptions'])

            else:
                intRat = None

            review = model.Review(
                user=session['username'],
                company=model.to_company_obj(comp),
                position=form['position'],
                job_cat=form['jobCategory'],
                education=form['education'],
                pay=float(form['payAmount']),
                location=location, #trick to readjust date from YYYY-MM-DD -> MM-DD-YYYY
                start_date=list(map(lambda x: f"{x[1]}-{x[2]}-{x[0]}", [form['startDate'].split("-")]))[0],
                company_rating=int(form['companyRatingOptions']),
                work_rat=workRat,
                culture_rat=cultRat,
                interview_rat=intRat,
                bonuses=form['bonusesDescription'],
                interview_desc=form['interviewDescription'],
                intern_desc=form['internshipDescription'],
                offer=form['offerOptions'] == "true",
                accepted=form['acceptedOptions'] == "true" and form['offerOptions'] == "true",
                title="Title"
            )
            try:
                model.submit_review(review)
                flash('Review submitted!', "success")
            except:
                flash("Error submitting your review! Try again.",'danger')
                return redirect(request.referrer)

    user = db.users.find_one({'username':session['username']})
    return render_template(
        'submit_review.html',
        company=company_to_review,
        states=model.states,
        categories=model.job_categories,
        ed_levels=model.degrees,
        user=user)
