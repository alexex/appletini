from flask import Flask, redirect, url_for, render_template, request, flash
from flaskext.sqlalchemy import SQLAlchemy
from sqlalchemy import desc
from flaskext.login import LoginManager, login_user, logout_user, login_required, current_user
from flaskext.mail import Mail, Message

from werkzeug.contrib.atom import AtomFeed

from hashlib import md5
from textile import textile
from datetime import datetime

from flask_dashed.admin import Admin
from flask_dashed.ext.sqlalchemy import ModelAdminModule

# create the flask object
www = Flask(__name__)
admin = Admin(www)
# disable debug mode
www.debug = True
www.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:////tmp/test.db"
www.config['SECRET_KEY'] = "foobar"

#  this is some magic to hide secret config options
try:
   from secret import *
except ImportError:
   pass
# enable database
db = SQLAlchemy(www)

# enable mail
mail = Mail(www)

# create login manager and configure it
login = LoginManager()
login.setup_app(www, add_context_processor=True)
login.login_view = 'login'


class User(db.Model):
	'''login & user stuff'''
	id = db.Column(db.Integer, primary_key=True)
	email = db.Column(db.String(60), unique=True)
	password = db.Column(db.String(32))
	firstname = db.Column(db.String(20))
	lastname = db.Column(db.String(30))
	active = db.Column(db.Boolean)
	authenticated = db.Column(db.Boolean)
	
	def __init__(self, email="", password="", firstname="", lastname=""):
		self.email = email
		self.password = md5(password).hexdigest()
		self.firstname = firstname
		self.lastname = lastname
		self.active = True
		self.authenticated = False
		
	def __repr__(self):
		return '<User: %s>' % self.email
		
	def authenticate(self, password):
		if self.password == md5(password).hexdigest():
			return True
		else:
			return False
		
	# the loginmanager specific stuff
	def is_authenticated(self):
		return self.authenticated
		
	def is_active(self):
		return self.active
		
	def is_anonymous(self):
		return False
	
	def get_id(self):
		return self.id	

def authenticate_user(email, password):
	user = User.query.filter_by(email=email)
	if user is None:
		return None
	elif user.password != password:
		return None
	else:
		return user 

@login.user_loader
def user_loader(id):
		return User.query.get(id)


@www.route('/login', methods=["GET", "POST"])
def login():
	if request.method == 'POST':
		user = User.query.filter_by(email=request.form['email']).first()
		if user is None:
			flash('Login failed.')
		elif user.authenticate(request.form['password']):
			user.authenticated = True
			db.session.commit()
			login_user(user)
			flash('Login succeeded.')
			return redirect(request.args.get("next") or url_for('home'))
		else:
			flash('Login failed.')
	return render_template('login.html')


@www.route('/logout')
@login_required
def logout():
	current_user.authenticated = False
	db.session.commit()
	logout_user()
	flash('Logout succeeded.')
	return redirect(url_for('home'))

@www.route('/projects')
def projectindex():
	'''projects page'''
	return render_template('comingsoon.html', what='Projects')



@www.route('/contact', methods=['GET', 'POST'])
def contact():
	'''contact app'''
	if request.method == 'POST':
		if request.form['name'] == '':
			flash('Please enter a valid name.')
		if request.form['email'] == '':
			flash('Please enter a valid e-mail-address.')
		elif request.form['text'] == '':
			flash('Please enter a valid message.')
		else:
			msg = Message('Contact form input',
				sender = (request.form['name'], request.form['email']),
				recipients = ['alexander.jung-loddenkemper@julo.ch'],
				body = request.form['text'],
			)
			mail.send(msg)
			flash('Message sent.')
			return redirect(url_for('home'))
	return render_template('contact.html')

# own blog stuff

class Post(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	title = db.Column(db.String(60))
	body = db.Column(db.Text)
	created = db.Column(db.DateTime)
	
	author = db.Column(db.Integer, db.ForeignKey('user.id'))
	
	def __init__(self, title="", body="", author=""):
		self.title = title
		self.body = body
		self.created = datetime.utcnow()
		self.author = author

	def __repr__(self):
		return '<Post: %r>' % self.title
		
class PostModule(ModelAdminModule):
	model = Post
	db_session = db.session

post_module = admin.register_module(PostModule, '/posts', 'posts', 'Posts')

@post_module.secure(http_code=401)
def login_required():
	return current_user.is_authenticated()

@www.route('/blog')
def postindex():
	posts = Post.query.order_by(desc('created')).all()
	for post in posts:
		author = User.query.get(post.author)
		post.author_name = author.firstname + ' ' + author.lastname
		post.body = textile(post.body)
	return render_template('blog/index.html', posts=posts)
	
@www.route('/blog/post/<int:id>')
def postshow(id):
	post = Post.query.get_or_404(id)
	author = User.query.get(post.author)
	post.author_name = author.firstname + ' ' + author.lastname
	post.body = textile(post.body)
	return render_template('blog/show.html', post=post)
	
@www.route('/blog/atom')
def postatom():
	'''atom feed for my blog'''
	feed = AtomFeed('julo.ch', feed_url=request.url, url=request.host_url, subtitle='It\'s mine.')
	for post in Post.query.order_by(desc('created')).limit(10).all():
		author = User.query.get(post.author)
		post.author_name = author.firstname + ' ' + author.lastname
		feed.add(post.title, textile(post.body), content_type='html', author=post.author_name, url=url_for('postshow', id=post.id), id=post.id, updated=post.created, published=post.created)
	return feed.get_response()


class Page(db.Model):
	'''own textile flatpages stuff'''
	id = db.Column(db.Integer, primary_key=True)
	path = db.Column(db.String(80))
	title = db.Column(db.String(80))
	body = db.Column(db.Text)
	
	def __init__(self, path="", title="", body=""):
		self.path = path
		self.title = title
		self.body = body
		
	def __repr__(self):
		return '<Page: %r>' % self.path

class PageModule(ModelAdminModule):
	model = Page
	db_session = db.session

page_module = admin.register_module(PageModule, '/pages', 'pages', 'Pages')

@page_module.secure(http_code=401)
def login_required():
	return current_user.is_authenticated()

@www.route('/<path>')
def pageshow(path):
	page = Page.query.filter_by(path=path).first_or_404()
	return render_template('pages/show.html', content=textile(page.body), title=page.title)


# stuff independent of the sections

@www.route('/')
def home():
	'''home page'''
	return redirect(url_for('postindex'))

# create non existent tables
db.create_all()

@www.errorhandler(404)
def page_not_found(error):
	'''404 page'''
	return render_template('pagenotfound.html'), 404
	
# run the developement server
if __name__ == '__main__':
    www.run(host='0.0.0.0')
