from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
from allauth.account.utils import perform_login
from django.shortcuts import redirect
from django.contrib import messages
from allauth.exceptions import ImmediateHttpResponse

User = get_user_model()

class ScentoraSocialAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # 1. If this social account is already linked, proceed normally
        if sociallogin.is_existing:
            return

        # 2. Extract email from Google account data
        email = sociallogin.user.email
        if not email:
            return

        try:
            # 3. Check if user exists in the Decora database
            user = User.objects.get(email=email)

            # 4. Check Blocked Status
            if not user.is_active or getattr(user, 'is_blocked', False):
                messages.error(request, "This account has been restricted.")
                raise ImmediateHttpResponse(redirect('user_login'))

            # 5. Connect Google account to the existing Email/Password user
            sociallogin.connect(request, user)
            
            # 6. Log them in
            perform_login(request, user, email_verification='none')
            
            # 7. Explicitly force redirect to the dashboard (index.html)
            # Ensure 'home' matches the name in your urls.py
            raise ImmediateHttpResponse(redirect('home'))

        except User.DoesNotExist:
            # New user: let Allauth handle the creation of a new account
            pass