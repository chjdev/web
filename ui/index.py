#!/usr/bin/env python
# -*- coding: utf-8 -*-
from flask import render_template, request, flash, Blueprint, g
from flask_security import current_user
from flask_mail import Message
from flask_modules.mail import mail
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import InputRequired, Email

from config.env import Environment

index = Blueprint('index', __name__)
web_env = Environment('WEB')


class ContactForm(FlaskForm):
    email = StringField("Email", [InputRequired("Please enter your email address."),
                                  Email("A valid email address is required.")])
    message = TextAreaField("Message", [InputRequired("Please add a message.")])
    submit = SubmitField("Send")


@index.route('/mail', methods=['POST'])
def mail():
    contact_form = ContactForm()
    if request.method == 'POST':
        #        if session.get('already_sent', False):
        #            flash('Already got your message, thanks!')
        #        elif contact_form.validate():
        #            flash('Thank you for contacting us!')
        #            msg = Message(subject='Message From: %s' % contact_form.email.data,
        #                          body="%(sender)s\n%(message)s" % dict(
        #                              sender=contact_form.email.data, message=contact_form.message.data),
        #                          sender=contact_form.email.data,
        #                          recipients=["info@fanlens.io"])
        #            mail.send(msg)
        #            session['already_sent'] = True
        msg = Message(subject='Message From: %s' % contact_form.email.data,
                      body="%(sender)s\n%(message)s" % dict(
                          sender=contact_form.email.data, message=contact_form.message.data),
                      sender=contact_form.email.data,
                      recipients=["info@fanlens.io"])
        mail.send(msg)
        flash('Thank you for contacting us!')
    return render_template('landing/index.html', contact_form=contact_form)


@index.route('/', defaults={'path': ''})
@index.route('/<path:path>')
def root(path):
    return render_template('index.html',
                           api_key=(current_user.get_auth_token()
                                    if current_user.has_role('tagger')
                                    else g.demo_user.get_auth_token()),
                           path=path)