Google
======

Go to:

https://www.google.com/accounts/ManageDomains

Sign in.

Add a new Domain:

domain.com

Manage the domain - you'll need to handle their verification process. After
you've verified the domain, you'll need to activate it. For the Target
URL path prefix put:

http://domain.com/velruse/logged_in

Once you've done this, you're presented with your OAuth Consumer Key
and OAuth Consumer Secret.

Modify your **CONFIG.yaml** file to include the following:

::

    Google:
        OAuth Consumer Key: domain.com
        OAuth Consumer Secret: (OAuth Consumer Secret)
