import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'datahub.settings')
django.setup()

from api.models import Skill, SkillFile

skill = Skill.objects.get(name='nedco-format-1')
print(f'Skill: {skill.name}')
print(f'Description: {skill.description}')
print(f'Entry point: {skill.entry_point}')
print(f'Output type: {skill.output_type}')
print(f'\nFiles:')
for f in skill.files.all():
    print(f'  - {f.path} ({f.content_type})')

print(f'\n=== SKILL.md ===')
skill_md = skill.files.filter(path__iexact='SKILL.md').first()
if skill_md:
    print(skill_md.content)
else:
    print('No SKILL.md')

print(f'\n=== scripts/bfev_pipeline.py ===')
pipeline = skill.files.filter(path='scripts/bfev_pipeline.py').first()
if pipeline:
    print(pipeline.content)
else:
    print('No scripts/bfev_pipeline.py')

print(f'\n=== All script files ===')
for f in skill.files.filter(path__endswith='.py'):
    print(f'--- {f.path} ---')
    print(f.content[:500] if len(f.content) > 500 else f.content)
    print()
