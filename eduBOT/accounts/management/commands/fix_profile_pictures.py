from django.core.management.base import BaseCommand
from accounts.models import TeacherProfile, StudentProfile
from django.conf import settings
import os
import shutil

class Command(BaseCommand):
    help = 'Fix profile picture paths and copy static profile pictures to media'

    def handle(self, *args, **options):
        # Copy static profile pictures to media directory
        static_pics = {
            'sangu.jpg': 'sangamesh',
            'satya.jpg': 'satya',
            'vamshi.jpg': 'vamshi',
            'team.jpg': 'team'
        }
        
        for pic, username in static_pics.items():
            src = os.path.join(settings.BASE_DIR, 'eduBOT/static/profile_pics', pic)
            if os.path.exists(src):
                # Create user directory in media
                dest_dir = os.path.join(settings.MEDIA_ROOT, 'profile_pics', username)
                os.makedirs(dest_dir, exist_ok=True)
                
                # Copy file
                dest = os.path.join(dest_dir, pic)
                shutil.copy2(src, dest)
                self.stdout.write(f'Copied {pic} to {dest}')

        # Update profile pictures in database
        for profile in TeacherProfile.objects.all():
            if profile.user.username in ['sangamesh', 'satya', 'vamshi']:
                profile.profile_picture = f'profile_pics/{profile.user.username}/{profile.user.username}.jpg'
                profile.save()
                self.stdout.write(f'Updated profile picture for {profile.user.username}') 