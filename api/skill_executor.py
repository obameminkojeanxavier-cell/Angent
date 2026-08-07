"""
Moteur d'exécution des skills.

Ce module implémente un système d'exécution sophistiqué pour les skills importés
via ZIP, permettant de distinguer entre les fichiers d'interface, les modèles,
les ressources et les générateurs, et de produire des livrables dans différents
formats (HTML, PDF, Markdown, JSON, etc.).
"""
import os
import re
import sys
import tempfile
import subprocess
import zipfile
from pathlib import Path


def detect_skill_root(extract_dir: Path) -> Path:
    """Détecte automatiquement la racine du skill en cherchant SKILL.md."""
    skill_files = list(extract_dir.rglob("SKILL.md"))
    
    if not skill_files:
        raise ValueError("Aucun fichier SKILL.md trouvé dans le package.")
    
    if len(skill_files) > 1:
        raise ValueError("Plusieurs racines de skill détectées dans le package.")
    
    return skill_files[0].parent


def validate_zip_structure(extract_dir: Path) -> None:
    """Valide la structure du ZIP extrait."""
    # Vérifier que SKILL.md existe
    skill_files = list(extract_dir.rglob("SKILL.md"))
    if not skill_files:
        raise ValueError("Aucun fichier SKILL.md trouvé dans le package.")
    
    if len(skill_files) > 1:
        raise ValueError("Plusieurs racines de skill détectées dans le package.")
    
    # Vérifier l'absence de chemins dangereux (.. dans les chemins relatifs)
    for file_path in extract_dir.rglob("*"):
        if file_path.is_file():
            try:
                relative = file_path.relative_to(extract_dir)
                # Vérifier que le chemin résolu reste dans extract_dir
                resolved = (extract_dir / relative).resolve()
                if not str(resolved).startswith(str(extract_dir.resolve())):
                    raise ValueError(f"Chemin dangereux détecté : {relative}")
            except ValueError:
                # Erreur lors du calcul du chemin relatif
                raise ValueError(f"Chemin invalide détecté : {file_path}")


class SkillExecutor:
    """Moteur d'exécution des skills."""
    
    def __init__(self, skill, params):
        self.skill = skill
        self.params = params
        self.files = {f.path: f for f in skill.files.all()}
    
    def execute(self):
        """Exécute le skill et retourne le résultat."""
        # Déterminer le type d'exécution selon le point d'entrée
        entry_point = self.skill.entry_point
        
        if not entry_point:
            # Auto-détection du point d'entrée
            entry_point = self._detect_entry_point()
        
        if not entry_point:
            raise ValueError("Aucun point d'entrée trouvé dans le skill")
        
        # Exécuter selon le type de fichier
        if entry_point.endswith('.py'):
            return self._execute_python(entry_point)
        elif entry_point.endswith('.html'):
            return self._execute_html_template(entry_point)
        elif entry_point.endswith('.md'):
            return self._execute_markdown(entry_point)
        else:
            # Fallback : traiter comme template
            return self._execute_template(entry_point)
    
    def _detect_entry_point(self):
        """Détecte automatiquement le point d'entrée du skill."""
        # Priorité : scripts/*.py > generator.py > main.py > template.html > index.html > SKILL.md
        candidates = [
            'scripts/bfev_pipeline.py',
            'scripts/pipeline.py',
            'scripts/generator.py',
            'scripts/main.py',
            'generator.py',
            'main.py',
            'run.py',
            'execute.py',
            'template.html',
            'index.html',
            'output.html',
            'SKILL.md',
        ]
        
        for candidate in candidates:
            if candidate in self.files:
                return candidate
        
        # Chercher n'importe quel script dans scripts/
        for path in sorted(self.files.keys()):
            if path.startswith('scripts/') and path.endswith('.py'):
                return path
        
        # Sinon, prendre le premier fichier non-MD
        for path in sorted(self.files.keys()):
            if not path.lower().endswith('.md'):
                return path
        
        return None
    
    # Variantes de noms employées par les agents -> nom canonique attendu.
    PARAM_ALIASES = {
        'text': 'content', 'texte': 'content', 'contenu': 'content',
        'corps': 'content', 'body': 'content', 'message': 'content',
        'titre': 'title', 'objet': 'title', 'subject': 'title',
        'sous_titre': 'subtitle', 'sous-titre': 'subtitle', 'soustitre': 'subtitle',
        'entite': 'entity', 'entité': 'entity', 'societe': 'entity',
        'société': 'entity', 'company': 'entity', 'organisation': 'entity',
        'type': 'document_type', 'type_document': 'document_type',
        'type_de_document': 'document_type', 'doc_type': 'document_type',
        'documenttype': 'document_type',
    }

    # Clés par lesquelles un agent exprime le FORMAT DE SORTIE souhaité.
    # Important : dans bfev_pipeline.py, `--format` désigne le format de la
    # SOURCE (import_file). Passer « --format pdf » fait donc croire au pipeline
    # que l'entrée est un PDF, d'où son rejet. On interprète ces clés ici au lieu
    # de les transmettre aveuglément.
    OUTPUT_FORMAT_KEYS = {
        'output_format', 'output_type', 'target_format', 'export_format',
        'export', 'to', 'format', 'sortie', 'format_sortie',
    }
    # Formats de sortie reconnus (le DOCX est la sortie par défaut du pipeline).
    _PDF_VALUES = {'pdf', 'application/pdf', '.pdf'}
    _DOCX_VALUES = {'docx', 'word', 'doc', '.docx',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}

    def _normalize_params(self, raw):
        """
        Harmonise les paramètres fournis par un agent :
        - applique les alias de noms (titre -> title, contenu -> content…) ;
        - traduit l'intention de format de sortie en flag `pdf` ;
        - conserve un éventuel format de SOURCE légitime (markdown, html…).
        """
        params = {}
        want_pdf = False
        source_format = None

        for key, value in (raw or {}).items():
            k = str(key).strip()
            low = k.lower()

            if low in self.OUTPUT_FORMAT_KEYS:
                val = str(value).strip().lower()
                if val in self._PDF_VALUES:
                    want_pdf = True
                elif val in self._DOCX_VALUES or val == '':
                    pass  # sortie DOCX = comportement par défaut
                elif low == 'format':
                    # Valeur non reconnue comme format de sortie : c'est le
                    # format de la source (markdown, html, txt…).
                    source_format = val
                continue

            if low == 'pdf':
                want_pdf = want_pdf or bool(value) and str(value).lower() not in ('false', '0', 'no')
                continue

            params[self.PARAM_ALIASES.get(low, k)] = value

        if source_format:
            params['format'] = source_format
        if want_pdf:
            params['pdf'] = True
        return params

    def _execute_python(self, entry_point):
        """Exécute un script Python du skill, avec TOUTES ses ressources."""
        import logging
        logger = logging.getLogger(__name__)

        if entry_point not in self.files:
            raise FileNotFoundError(f"Fichier introuvable : {entry_point}")

        # Créer un environnement temporaire
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Restituer l'arborescence complète du skill : fichiers texte ET
            # ressources binaires (logos, modèles DOCX…). Sans les binaires, les
            # pipelines échouent avec « logo introuvable ».
            for path, file_obj in self.files.items():
                file_obj.write_to(tmpdir_path / path)

            # Valider la structure et détecter la racine du skill
            validate_zip_structure(tmpdir_path)
            skill_root = detect_skill_root(tmpdir_path)

            # Journalisation de diagnostic : racine réelle et inventaire restitué.
            written = sorted(
                p.relative_to(skill_root).as_posix()
                for p in skill_root.rglob('*') if p.is_file()
            )
            logger.info("skill=%s skill_root=%s", self.skill.name, skill_root)
            logger.info("skill_files_written=%s", written)
            missing_binaries = [
                p for p, f in self.files.items()
                if f.is_binary and not (tmpdir_path / p).exists()
            ]
            if missing_binaries:
                logger.warning("ressources binaires manquantes=%s", missing_binaries)

            # Mapping des paramètres vers les arguments CLI (selon bfev_pipeline.py)
            param_mapping = {
                'content': 'text',
                'document_type': 'document-type',
                'entity': 'entity',
                'title': 'title',
                'subtitle': 'subtitle',
                'date': 'date',
                'template': 'template',
                'logo': 'logo',
                'format': 'format',
                'catalog': 'catalog',
                'entity_catalog': 'entity-catalog',
            }

            # Paramètres booléens qui n'ont pas de valeur (selon bfev_pipeline.py)
            boolean_params = {'pdf', 'analyze_only', 'no_cache'}

            # Les agents (ChatGPT, Claude…) nomment les champs librement : on
            # normalise les variantes courantes vers les noms attendus.
            params = self._normalize_params(self.params)

            # Générer automatiquement un chemin de sortie si non fourni.
            output_path = params.get('output')
            if not output_path:
                # Le dossier de sortie vit DANS le répertoire temporaire de cette
                # exécution : il est créé par le processus courant (donc pas de
                # « Permission denied » quand root et www-data se partagent un
                # chemin fixe comme /tmp/datahub-skills) et il est supprimé
                # automatiquement à la fin — pas d'accumulation sur le disque.
                output_dir = tmpdir_path / '_datahub_output'
                output_dir.mkdir(parents=True, exist_ok=True)

                # Générer un nom de fichier sécurisé
                document_type = str(params.get('document_type') or 'document').replace('_', '-')
                document_type = re.sub(r'[^A-Za-z0-9._-]', '-', document_type) or 'document'
                output_filename = f"{document_type}.docx"
                output_path = str(output_dir / output_filename)
            
            # Résoudre le script : `entry_point` est un chemin tel que stocké en
            # base, qui peut inclure (ou non) le dossier racine du skill. On tente
            # les deux bases, puis une recherche par nom de fichier.
            script_path = None
            for candidate in (tmpdir_path / entry_point, skill_root / entry_point):
                if candidate.is_file():
                    script_path = candidate
                    break
            if script_path is None:
                matches = list(skill_root.rglob(Path(entry_point).name))
                if matches:
                    script_path = matches[0]
            if script_path is None:
                raise FileNotFoundError(
                    f"Script introuvable : {entry_point} (racine détectée : {skill_root})"
                )

            # Construire les arguments de ligne de commande.
            # `sys.executable` = l'interpréteur qui fait tourner DataHub (celui du
            # venv). Indispensable : sous systemd le venv n'est pas activé, donc
            # « python » n'existe pas, et « python3 » serait l'interpréteur système
            # dépourvu des dépendances du skill (PyYAML, python-docx…).
            args = [sys.executable, str(script_path)]
            
            # Ajouter le chemin de sortie (obligatoire selon bfev_pipeline.py)
            args.append('--output')
            args.append(output_path)
            
            # Ajouter les paramètres comme arguments
            for key, value in params.items():
                if key == 'output':
                    continue  # déjà passé ci-dessus
                cli_key = param_mapping.get(key, key).replace('_', '-')

                if key in boolean_params or isinstance(value, bool):
                    # Un flag ne s'ajoute que s'il est demandé.
                    if value:
                        args.append(f'--{cli_key}')
                elif value is not None and value != '':
                    args.append(f'--{cli_key}')
                    args.append(str(value))

            # Préparer les variables d'environnement
            env = os.environ.copy()
            for key, value in params.items():
                env[f'SKILL_{key.upper()}'] = str(value)

            # LibreOffice (conversion DOCX -> PDF) exige un HOME inscriptible pour
            # créer son profil utilisateur. Sous www-data, le HOME système ne l'est
            # pas forcément : on lui en fournit un, jetable, dans le tmpdir.
            home_dir = tmpdir_path / '_home'
            (home_dir / '.config').mkdir(parents=True, exist_ok=True)
            (home_dir / '.cache').mkdir(parents=True, exist_ok=True)
            env['HOME'] = str(home_dir)
            env['XDG_CONFIG_HOME'] = str(home_dir / '.config')
            env['XDG_CACHE_HOME'] = str(home_dir / '.cache')
            env.setdefault('TMPDIR', str(tmpdir_path))
            
            # Journaliser la commande exacte, le cwd et la sortie attendue.
            logger.info("script=%s cwd=%s output=%s", script_path, skill_root, output_path)
            logger.info("command=%s", ' '.join(args))

            # Exécuter le script depuis la racine du skill.
            # Timeout large : la conversion PDF via LibreOffice est lente au
            # premier lancement (initialisation du profil).
            try:
                result = subprocess.run(
                    args,
                    cwd=skill_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=180
                )

                if result.returncode != 0:
                    logger.error("skill=%s stderr=%s", self.skill.name, result.stderr)
                    raise RuntimeError(f"Erreur d'exécution : {result.stderr}")

                # Inventorier les livrables : d'abord le dossier de sortie (le
                # pipeline y écrit le DOCX *et* le PDF converti, souvent sous un
                # autre nom que --output), puis les fichiers apparus dans le skill.
                candidates = []
                out_dir = Path(output_path).parent
                if out_dir.is_dir():
                    candidates.extend(p for p in out_dir.rglob('*') if p.is_file())
                for path_obj in skill_root.rglob('*'):
                    if not path_obj.is_file():
                        continue
                    rel = path_obj.relative_to(skill_root).as_posix()
                    # Ignorer les fichiers d'origine du skill…
                    if rel in self.files:
                        continue
                    # …ainsi que nos dossiers internes (profil LibreOffice, et la
                    # sortie déjà inventoriée ci-dessus).
                    if rel.startswith(('_home/', '_datahub_output/', '__pycache__/')):
                        continue
                    candidates.append(path_obj)

                logger.info("livrables=%s", [str(p) for p in candidates])

                # PDF prioritaire, puis DOCX (le plus récent d'abord).
                def _newest(paths):
                    return sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)[0]

                pdf_files = [p for p in candidates if p.suffix.lower() == '.pdf']
                if pdf_files:
                    chosen = _newest(pdf_files)
                    logger.info("livrable_retenu=%s (pdf)", chosen)
                    return {
                        'content': chosen.read_bytes(),
                        'content_type': 'application/pdf',
                        'output_type': 'pdf',
                        'filename': chosen.name,
                    }

                docx_files = [p for p in candidates if p.suffix.lower() == '.docx']
                if docx_files:
                    chosen = _newest(docx_files)
                    logger.info("livrable_retenu=%s (docx)", chosen)
                    return {
                        'content': chosen.read_bytes(),
                        'content_type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        'output_type': 'docx',
                        'filename': chosen.name,
                    }
                
                # Sinon, retourner stdout
                output = result.stdout
                output_type = self._detect_output_type(output)
                
                return {
                    'content': output,
                    'content_type': output_type,
                    'output_type': output_type,
                }
            except subprocess.TimeoutExpired:
                raise RuntimeError("Timeout lors de l'exécution du script")
    
    def _execute_html_template(self, entry_point):
        """Exécute un template HTML."""
        file_obj = self.files.get(entry_point)
        if not file_obj:
            raise FileNotFoundError(f"Fichier introuvable : {entry_point}")
        
        content = file_obj.content
        
        # Remplacer les paramètres dans le template
        for key, value in self.params.items():
            content = content.replace(f'{{{key}}}', str(value))
            content = content.replace(f'{{{{ {key} }}}}', str(value))
        
        # Si le skill demande du PDF, convertir
        if self.skill.output_type == 'pdf':
            return self._convert_to_pdf(content)
        
        return {
            'content': content,
            'content_type': 'text/html',
            'output_type': 'html',
        }
    
    def _execute_markdown(self, entry_point):
        """Exécute un template Markdown."""
        file_obj = self.files.get(entry_point)
        if not file_obj:
            raise FileNotFoundError(f"Fichier introuvable : {entry_point}")
        
        content = file_obj.content
        
        # Remplacer les paramètres
        for key, value in self.params.items():
            content = content.replace(f'{{{key}}}', str(value))
        
        return {
            'content': content,
            'content_type': 'text/markdown',
            'output_type': 'markdown',
        }
    
    def _execute_template(self, entry_point):
        """Exécute un template générique."""
        file_obj = self.files.get(entry_point)
        if not file_obj:
            raise FileNotFoundError(f"Fichier introuvable : {entry_point}")
        
        content = file_obj.content
        
        # Remplacer les paramètres
        for key, value in self.params.items():
            content = content.replace(f'{{{key}}}', str(value))
        
        return {
            'content': content,
            'content_type': file_obj.content_type,
            'output_type': self.skill.output_type,
        }
    
    def _detect_output_type(self, content):
        """Détecte le type de contenu."""
        content_lower = content.lower()
        
        if content_lower.startswith('<!doctype html') or content_lower.startswith('<html'):
            return 'text/html'
        elif content_lower.startswith('{') or content_lower.startswith('['):
            return 'application/json'
        elif content_lower.startswith('#') or content_lower.startswith('##'):
            return 'text/markdown'
        else:
            return 'text/plain'
    
    def _convert_to_pdf(self, html_content):
        """Convertit le contenu HTML en PDF."""
        try:
            # Essayer avec weasyprint
            import weasyprint
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                pdf_path = tmp.name
            
            weasyprint.HTML(string=html_content).write_pdf(pdf_path)
            
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
            
            os.unlink(pdf_path)
            
            return {
                'content': pdf_content,
                'content_type': 'application/pdf',
                'output_type': 'pdf',
            }
        except ImportError:
            # Fallback : essayer avec wkhtmltopdf
            try:
                with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as html_tmp:
                    html_tmp.write(html_content.encode('utf-8'))
                    html_path = html_tmp.name
                
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as pdf_tmp:
                    pdf_path = pdf_tmp.name
                
                subprocess.run(
                    ['wkhtmltopdf', html_path, pdf_path],
                    capture_output=True,
                    timeout=30
                )
                
                with open(pdf_path, 'rb') as f:
                    pdf_content = f.read()
                
                os.unlink(html_path)
                os.unlink(pdf_path)
                
                return {
                    'content': pdf_content,
                    'content_type': 'application/pdf',
                    'output_type': 'pdf',
                }
            except (FileNotFoundError, subprocess.SubprocessError):
                # Si PDF non disponible, retourner HTML avec avertissement
                return {
                    'content': html_content,
                    'content_type': 'text/html',
                    'output_type': 'html',
                    'warning': 'Conversion PDF non disponible, HTML retourné à la place',
                }
