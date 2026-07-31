import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'datahub.settings')
django.setup()

from api.models import Skill, SkillFile

skill = Skill.objects.get(name='nedco-format-1')
pipeline = skill.files.filter(path='scripts/bfev_pipeline.py').first()
if pipeline:
    print(pipeline.content)
else:
    print('No scripts/bfev_pipeline.py')
