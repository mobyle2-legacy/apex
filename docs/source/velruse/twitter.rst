Twitter
=======

Go to:

http://dev.twitter.com/apps/new

Sign in.

Application Name, Description and Website are not critical, but, are required
fields. Set the Callback URL to:

http://yourdomain.com/velruse/logged_in

After you agree to the terms, you're presented with a page that contains your
Consumer Key and Consumer Secret.

Modify your **CONFIG.yaml** file to include the following:

::

    Twitter:
        Consumer Key: (key from the resulting page)
        Consumer Secret: (secret from the resulting page)
