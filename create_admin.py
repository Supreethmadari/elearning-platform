import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from accounts.models import User

username = os.environ.get('ADMIN_USERNAME', 'admin')
email = os.environ.get('ADMIN_EMAIL', 'admin@cyanopy.com')
password = os.environ.get('ADMIN_PASSWORD', 'Admin@2026')

user, created = User.objects.get_or_create(
    username=username,
    defaults={
        'email': email,
        'first_name': 'Admin',
        'last_name': 'Cyanopy',
        'is_staff': True,
        'is_superuser': True,
        'is_trainer': True,
        'is_verified': True,
    }
)

# Ensure all permissions and password are set
user.email = email
user.is_staff = True
user.is_superuser = True
user.is_trainer = True
user.is_verified = True
user.set_password(password)
user.save()

action = "Created" if created else "Updated"
print(f"==================================================")
print(f" [CYANOPY ADMIN] {action} admin superuser: {username}")
print(f"==================================================")
