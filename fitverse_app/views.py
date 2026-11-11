import json
import logging
import os
from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.shortcuts import render, get_object_or_404, redirect
from django.http import FileResponse, Http404, JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from .models import (
    Category, Design, UserMeasurement, SavedLook, Favorite, VirtualTryOn,
    WardrobeItem,
)
from .services.fashn_vton import FashnVtonError, generate_try_on
from .services.gemini_ai import (
    GeminiError,
    generate_stylist_response,
    generate_try_on as generate_gemini_try_on,
    recommend_wardrobe_outfits,
    tag_wardrobe_image,
)
from .services.bodygram import BodygramError, estimate_measurements, normalize_photo
from .services.wardrobe import WardrobeImageError, prepare_photo
from .services import look360
from .services.look360 import Look360Error

logger = logging.getLogger(__name__)


class TryOnError(Exception):
    """Raised when no configured provider can render a try-on."""


def get_session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def wardrobe_owner_filter(request):
    """Match wardrobe rows for the signed-in user, or this browser session."""
    if request.user.is_authenticated:
        return Q(user=request.user)
    return Q(session_key=get_session_key(request))


def _wardrobe_item_for(request, item_id):
    return get_object_or_404(
        WardrobeItem.objects.filter(wardrobe_owner_filter(request)), pk=item_id
    )


def _wardrobe_payload(item):
    return {
        'id': item.id,
        'name': item.name or 'Untitled piece',
        'category': item.category,
        'category_label': item.get_category_display(),
        'colours': item.colours or [],
        'pattern': item.pattern,
        'formality': item.formality,
        'seasons': item.seasons or [],
        'style_tags': item.style_tags or [],
        'notes': item.notes,
        'tagged': item.tagged,
        'wear_count': item.wear_count,
        'thumb_url': reverse('wardrobe_item_thumb', args=[item.id]),
        'photo_url': reverse('wardrobe_item_photo', args=[item.id]),
    }


def _generate_try_on(*, person_image, garment_image, category, garment_photo_type):
    """Render a try-on, falling back from Gemini to FASHN Try-On.

    Returns a ``(result_url, provider)`` tuple. Gemini is only attempted when it
    is the configured provider and an API key is present; any Gemini failure is
    logged and retried once through the FASHN Space.
    """
    provider = (
        getattr(settings, 'TRYON_PROVIDER', '')
        or getattr(settings, 'AI_PROVIDER', 'gemini')
    )
    use_gemini = provider == 'gemini' and bool(getattr(settings, 'GEMINI_API_KEY', ''))
    failures = []

    if use_gemini:
        try:
            result_image = generate_gemini_try_on(
                person_image=person_image,
                garment_image=garment_image,
                category=category,
            )
            return result_image, 'gemini'
        except GeminiError as exc:
            logger.warning("Gemini try-on failed, falling back to FASHN Try-On: %s", exc)
            failures.append(f"Gemini: {exc}")
        finally:
            # Reading an upload advances its stream; rewind so the fallback can read it again.
            for upload in (person_image, garment_image):
                if hasattr(upload, 'seek'):
                    upload.seek(0)

    try:
        result_image = generate_try_on(
            person_image=person_image,
            garment_image=garment_image,
            category=category,
            garment_photo_type=garment_photo_type,
            num_timesteps=30,
            guidance_scale=1.5,
            seed=42,
            segmentation_free=True,
        )
        return result_image, 'fashn'
    except FashnVtonError as exc:
        logger.warning("FASHN try-on failed: %s", exc)
        failures.append(f"FASHN Try-On: {exc}")

    raise TryOnError("Could not generate the virtual try-on. " + " | ".join(failures))

# -------------------------------------------------------------
# PAGE VIEWS
# -------------------------------------------------------------

def home(request):
    featured_designs = Design.objects.filter(is_featured=True)[:4]
    categories = Category.objects.all()
    return render(request, 'home.html', {
        'featured_designs': featured_designs,
        'categories': categories,
    })

def dashboard(request):
    categories = Category.objects.all()
    recent_designs = Design.objects.all()[:4]
    session_key = get_session_key(request)
    saved_count = SavedLook.objects.filter(
        Q(user=request.user if request.user.is_authenticated else None) |
        Q(session_key=session_key)
    ).count()
    return render(request, 'dashboard.html', {
        'categories': categories,
        'recent_designs': recent_designs,
        'saved_count': saved_count,
    })

def designs_view(request):
    category_slug = request.GET.get('category', 'all')
    search_query = request.GET.get('q', '').strip()

    designs = Design.objects.all()
    if category_slug and category_slug != 'all':
        designs = designs.filter(category__slug=category_slug)
    
    if search_query:
        designs = designs.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(fabric__icontains=search_query) |
            Q(search_keywords__icontains=search_query)
        )

    categories = Category.objects.all()
    return render(request, 'designs.html', {
        'designs': designs,
        'categories': categories,
        'selected_category': category_slug,
        'search_query': search_query,
    })

def design_detail_view(request, slug):
    design = get_object_or_404(Design, slug=slug)
    related_designs = Design.objects.filter(category=design.category).exclude(id=design.id)[:4]
    return render(request, 'design_detail.html', {
        'design': design,
        'related_designs': related_designs,
    })


def _look360_ready(model_url, *, demo=False, message=''):
    payload = {'state': 'ready', 'model_url': model_url, 'demo': bool(demo)}
    if message:
        payload['message'] = message
    return JsonResponse(payload)


def _look360_model_name(slug):
    return f'look360/{slug}.glb'


def _look360_task_name(slug):
    return f'look360/{slug}.task'


def _load_look360_task(slug):
    """Read an in-flight Meshy task from cache or its tiny disk sidecar."""
    cache_key = f'look360:task:{slug}'
    task_id = cache.get(cache_key)
    if task_id:
        return task_id

    task_name = _look360_task_name(slug)
    if not default_storage.exists(task_name):
        return ''
    try:
        with default_storage.open(task_name, 'rb') as task_file:
            task_id = task_file.read(256).decode('utf-8').strip()
    except (OSError, UnicodeDecodeError):
        return ''
    if task_id:
        cache.set(cache_key, task_id, 60 * 60 * 24)
    return task_id


def _save_look360_task(slug, task_id):
    """Persist task identity before polling, so autoreloads cannot duplicate it."""
    cache.set(f'look360:task:{slug}', task_id, 60 * 60 * 24)
    task_name = _look360_task_name(slug)
    if default_storage.exists(task_name):
        default_storage.delete(task_name)
    default_storage.save(task_name, ContentFile(task_id.encode('utf-8')))


def _clear_look360_task(slug):
    cache.delete(f'look360:task:{slug}')
    task_name = _look360_task_name(slug)
    if default_storage.exists(task_name):
        default_storage.delete(task_name)


def _store_look360_model(slug, remote_url):
    """Persist Meshy's signed GLB locally; fall back to its URL if saving fails."""
    model_name = _look360_model_name(slug)
    if default_storage.exists(model_name):
        return default_storage.url(model_name)
    try:
        model_data = look360.download_model(remote_url)
        saved_name = default_storage.save(model_name, ContentFile(model_data))
        return default_storage.url(saved_name)
    except (Look360Error, OSError) as exc:
        logger.warning('Could not persist Look 360 model for %s: %s', slug, exc)
        return remote_url


@csrf_exempt
def api_look360(request, slug):
    """Relay for the design page's real 360 view (Meshy image-to-3D).

    POST ``{}``       -> start (or resume) the task for this design
    POST ``{task_id}`` -> poll an in-flight task

    Finished models are cached per design so seconds visits open instantly.
    With no API key configured the browser gets the demo model, clearly
    flagged, instead of a fake "real" 360.
    """
    design = get_object_or_404(Design, slug=slug)

    if request.method != 'POST':
        return JsonResponse({'state': 'failed', 'message': 'POST required.'}, status=405)

    local_model = _look360_model_name(slug)
    if default_storage.exists(local_model):
        _clear_look360_task(slug)
        return _look360_ready(default_storage.url(local_model))

    glb = cache.get(f'look360:glb:{slug}')
    if glb:
        served_glb = _store_look360_model(slug, glb) if glb.startswith('http') else glb
        cache.set(f'look360:glb:{slug}', served_glb, 60 * 60 * 24 * 7)
        _clear_look360_task(slug)
        return _look360_ready(served_glb)

    try:
        request_payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'state': 'failed', 'message': 'Invalid request.'}, status=400)

    task_id = str(request_payload.get('task_id') or '').strip()
    if len(task_id) > 200:
        return JsonResponse({'state': 'failed', 'message': 'Invalid 3D task id.'}, status=400)
    task_id = task_id or _load_look360_task(slug)

    if not look360.get_api_key():
        return _look360_ready(
            look360.DEMO_MODEL_URL,
            demo=True,
            message='Demo 360 view. Add a free Meshy API key (FITVERSE_3D_API_KEY) '
                    'to convert this exact design.',
        )

    if not task_id:
        try:
            task_id = look360.create_task(design.image_url)
        except Look360Error as exc:
            return JsonResponse({'state': 'failed', 'message': str(exc)}, status=502)
        _save_look360_task(slug, task_id)
    elif not _load_look360_task(slug):
        # A browser can reconnect with its task id after a server restart.
        _save_look360_task(slug, task_id)

    try:
        payload = look360.get_task(task_id)
    except Look360Error as exc:
        return JsonResponse({'state': 'failed', 'message': str(exc)}, status=502)

    status = (payload.get('status') or '').upper()

    if status == 'SUCCEEDED':
        glb = (payload.get('model_urls') or {}).get('glb') or ''
        if not glb:
            return JsonResponse({
                'state': 'failed',
                'message': 'The 3D service finished without a downloadable model.',
            }, status=502)
        glb = _store_look360_model(slug, glb)
        cache.set(f'look360:glb:{slug}', glb, 60 * 60 * 24 * 7)
        _clear_look360_task(slug)
        return _look360_ready(glb)

    if status in ('PENDING', 'IN_PROGRESS'):
        try:
            progress = int(payload.get('progress') or 0)
        except (TypeError, ValueError):
            progress = 0
        return JsonResponse({
            'state': 'working',
            'progress': progress,
            'task_id': task_id,
        })

    if status in ('FAILED', 'CANCELED'):
        _clear_look360_task(slug)
        message = (payload.get('task_error') or {}).get('message') or 'The 3D conversion failed.'
        return JsonResponse({'state': 'failed', 'message': message}, status=502)

    return JsonResponse({'state': 'working', 'progress': 0, 'task_id': task_id})

def tryon_view(request):
    preset_designs = Design.objects.filter(is_featured=True)[:6]
    return render(request, 'tryon.html', {
        'preset_designs': preset_designs,
    })

def measurements_view(request):
    session_key = get_session_key(request)
    measurements, _ = UserMeasurement.objects.get_or_create(
        user=request.user if request.user.is_authenticated else None,
        session_key=session_key if not request.user.is_authenticated else ''
    )
    bodygram_saved = None
    if measurements.bodygram_measurements or measurements.body_composition:
        bodygram_saved = {
            'scan_id': measurements.bodygram_scan_id,
            'all_measurements': measurements.bodygram_measurements or [],
            'body_composition': measurements.body_composition or {},
            'posture': measurements.bodygram_posture or {},
            'avatar_url': measurements.bodygram_avatar.url if measurements.bodygram_avatar else '',
            'height_cm': measurements.height_cm or 0,
            'front_photo_url': measurements.bodygram_front_photo.url if measurements.bodygram_front_photo else '',
            'right_photo_url': measurements.bodygram_right_photo.url if measurements.bodygram_right_photo else '',
            'scanned_at': (
                timezone.localtime(measurements.bodygram_scanned_at).strftime('%d %b %Y, %H:%M')
                if measurements.bodygram_scanned_at else ''
            ),
        }
    return render(request, 'measurements.html', {
        'measurements': measurements,
        'bodygram_saved': bodygram_saved,
    })

def style_intelligence_view(request):
    initial_garment = Design.objects.filter(category__slug='senator').first()
    if not initial_garment:
        initial_garment = Design.objects.first()
    categories = Category.objects.all()
    return render(request, 'style_intelligence.html', {
        'initial_garment': initial_garment,
        'categories': categories,
    })

def wardrobe_view(request):
    session_key = get_session_key(request)
    user_filter = Q(user=request.user) if request.user.is_authenticated else Q(session_key=session_key)
    saved_looks = SavedLook.objects.filter(user_filter)
    favorites = Favorite.objects.filter(user_filter).select_related('design')
    items = WardrobeItem.objects.filter(wardrobe_owner_filter(request))
    return render(request, 'wardrobe.html', {
        'saved_looks': saved_looks,
        'favorites': favorites,
        'wardrobe_items': items,
        'wardrobe_limit': getattr(settings, 'WARDROBE_MAX_ITEMS', 60),
    })

def profile_view(request):
    return render(request, 'profile.html')

def image_sources_view(request):
    return render(request, 'image_sources.html')

def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        # Authenticate via username or email
        user = authenticate(request, username=email, password=password)
        if not user:
            try:
                u = User.objects.get(email=email)
                user = authenticate(request, username=u.username, password=password)
            except User.DoesNotExist:
                user = None

        if user:
            login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'login.html', {'error': 'Invalid email or password.'})
    return render(request, 'login.html')

def signup_view(request):
    if request.method == 'POST':
        full_name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        if not email or not password:
            return render(request, 'signup.html', {'error': 'All fields are required.'})
        if User.objects.filter(email=email).exists():
            return render(request, 'signup.html', {'error': 'Email is already registered.'})
        
        username = email.split('@')[0]
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        user = User.objects.create_user(username=username, email=email, password=password, first_name=full_name)
        login(request, user)
        return redirect('dashboard')
    return render(request, 'signup.html')

def logout_view(request):
    logout(request)
    return redirect('home')

def forgot_password_view(request):
    if request.method == 'POST':
        return render(request, 'forgot_password.html', {'success': 'Password reset link sent if account exists.'})
    return render(request, 'forgot_password.html')


# -------------------------------------------------------------
# API ENDPOINTS
# -------------------------------------------------------------

@csrf_exempt
def api_stylist_chat(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = {}

    user_query = data.get('message', '').strip().lower()
    occasion = data.get('occasion', 'any')
    style_direction = data.get('style', 'any')
    budget = int(data.get('budget', 50000))

    designs = Design.objects.all()

    if 'senator' in user_query or style_direction == 'senator' or 'native' in user_query or 'traditional' in user_query:
        advice = "For modern Senator wear, structured Italian cashmere or high-twist polished wool delivers that sharp, non-creasing drape. Keep the collar clean and pair with tailored trousers that break just above your loafers."
        matched = designs.filter(category__slug__in=['senator', 'traditional'])
    elif 'ankara' in user_query or style_direction == 'ankara' or 'print' in user_query or 'wax' in user_query:
        advice = "With Ankara styling, the key is balancing vibrant patterns with thoughtful tailoring. Pair an authentic wax print with minimalist accessories (burnished gold or neutral leather) so the pattern speaks with elegance."
        matched = designs.filter(category__slug='ankara')
    elif 'wedding' in user_query or 'owambe' in user_query or occasion == 'wedding' or 'party' in user_query:
        advice = "For weddings and celebratory Owambes, rich jewel tones (Navy, Wine, Emerald, Champagne) are timeless favorites. A sharp Senator set or a regal Agbada gives an authoritative, celebratory presence."
        matched = designs.filter(category__slug__in=['senator', 'agbada', 'occasion'])
    elif 'work' in user_query or 'corporate' in user_query or 'office' in user_query or occasion == 'work' or 'suit' in user_query:
        advice = "For boardroom presence, choose tailored silhouettes with clean lines. Double-breasted cuts or structured blazer sets project authority while keeping you comfortable throughout a busy day."
        matched = designs.filter(category__slug__in=['formal', 'casual'])
    elif 'budget' in user_query or 'cheap' in user_query or 'under' in user_query:
        advice = f"Here are standout pieces that deliver luxury craftsmanship within your budget (up to ₦{budget:,}). Clean tailoring and premium finishing make all the difference."
        matched = designs.filter(price__lte=budget, price__gt=0)
    elif 'color' in user_query or 'colour' in user_query or 'navy' in user_query or 'wine' in user_query:
        advice = "Color harmony tip: Royal Navy pairs masterfully with Cognac brown and Silver. Wine and Burgundy look majestic when balanced with Champagne Gold or Charcoal accents. Emerald green looks striking against warm skin tones."
        matched = designs.filter(category__slug__in=['senator', 'occasion'])
    else:
        advice = "Here is a hand-picked recommendation that balances contemporary fit with rich texture. You can preview this look on a model using FASHN Try-On in the fitting studio on the right!"
        matched = designs.filter(is_featured=True)

    if not matched.exists():
        matched = designs[:2]
    else:
        matched = matched[:2]

    looks = []
    for d in matched:
        looks.append({
            'id': str(d.id),
            'slug': d.slug,
            'title': d.title,
            'category': d.category.slug,
            'vtonCategory': d.vton_category,
            'price': d.price,
            'priceLabel': d.price_label,
            'fabric': d.fabric,
            'silhouette': d.silhouette,
            'image': d.image_url,
            'description': d.description,
            'stylingAdvice': d.styling_advice,
        })

    if getattr(settings, 'AI_PROVIDER', 'gemini') == 'gemini' and getattr(settings, 'GEMINI_API_KEY', ''):
        try:
            advice, looks = generate_stylist_response(
                message=data.get('message', '').strip(),
                occasion=occasion,
                style=style_direction,
                budget=budget,
                catalog=looks,
            )
        except GeminiError as exc:
            return JsonResponse({'error': str(exc)}, status=503)

    return JsonResponse({
        'advice': advice,
        'looks': looks,
    })


@csrf_exempt
def api_vton_tryon(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    design_id = request.POST.get('design_id')
    model_preset = request.POST.get('model_preset', 'male-1')
    category = request.POST.get('category', 'one-pieces')
    person_image = request.FILES.get('person_image') or request.POST.get('person_image_url')
    garment_image = request.FILES.get('garment_image')
    session_key = get_session_key(request)

    if not person_image:
        return JsonResponse({'error': 'Upload a person image or select a model.'}, status=400)

    design = None
    if design_id:
        try:
            design = Design.objects.get(id=design_id)
        except (Design.DoesNotExist, ValueError):
            pass

    if garment_image is None:
        garment_image = request.POST.get('garment_image_url') or (design.image_url if design else None)
    if not garment_image:
        return JsonResponse({'error': 'Select a garment before generating a try-on.'}, status=400)

    try:
        result_image, provider = _generate_try_on(
            person_image=person_image,
            garment_image=garment_image,
            category=category,
            garment_photo_type=request.POST.get('garment_photo_type', 'model'),
        )
    except TryOnError as exc:
        return JsonResponse({'error': str(exc)}, status=503)

    tryon = VirtualTryOn.objects.create(
        user=request.user if request.user.is_authenticated else None,
        session_key=session_key,
        design=design,
        model_preset=model_preset,
        user_photo_url=person_image.name if hasattr(person_image, 'name') else person_image,
        result_photo_url=result_image,
        category=category,
        status='completed',
    )

    return JsonResponse({
        'status': 'success',
        'tryon_id': tryon.id,
        'result_image': result_image,
        'provider': provider,
        'garment_title': design.title if design else 'Active Look',
    })


@csrf_exempt
def api_save_measurements(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = {}

    session_key = get_session_key(request)
    m, _ = UserMeasurement.objects.get_or_create(
        user=request.user if request.user.is_authenticated else None,
        session_key=session_key if not request.user.is_authenticated else ''
    )

    for field in ['chest', 'waist', 'hips', 'shoulder', 'sleeve', 'inseam', 'neck']:
        if field in data and data[field]:
            try:
                setattr(m, field, float(data[field]))
            except ValueError:
                pass
    if 'unit' in data and data['unit'] in ['cm', 'in']:
        m.unit = data['unit']

    m.save()
    return JsonResponse({'status': 'saved'})


@csrf_exempt
def api_bodygram_measurements(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    front_photo = request.FILES.get('front_photo')
    right_photo = request.FILES.get('right_photo')
    if not front_photo or not right_photo:
        return JsonResponse(
            {'error': 'Upload both a front photo and a right-side photo.'}, status=400
        )

    allowed_types = {'image/jpeg', 'image/jpg', 'image/png'}
    for photo in (front_photo, right_photo):
        if getattr(photo, 'content_type', '') not in allowed_types:
            return JsonResponse(
                {'error': 'Bodygram accepts JPEG or PNG photos.'}, status=400
            )
        if photo.size > 12 * 1024 * 1024:
            return JsonResponse(
                {'error': 'Choose photos smaller than 12 MB each.'}, status=400
            )

    def as_float(name):
        try:
            return float(request.POST.get(name, ''))
        except (TypeError, ValueError):
            return None

    age = as_float('age')
    height_cm = as_float('height')
    weight_kg = as_float('weight')
    gender = (request.POST.get('gender') or '').strip().lower()

    if gender not in {'male', 'female'}:
        return JsonResponse({'error': 'Select a gender for the Bodygram scan.'}, status=400)
    if age is None or not 10 <= age <= 100:
        return JsonResponse({'error': 'Enter an age between 10 and 100.'}, status=400)
    if height_cm is None or not 50 <= height_cm <= 250:
        return JsonResponse({'error': 'Enter a height between 50 and 250 cm.'}, status=400)
    if weight_kg is None or not 20 <= weight_kg <= 300:
        return JsonResponse({'error': 'Enter a weight between 20 and 300 kg.'}, status=400)

    front_bytes = front_photo.read()
    right_bytes = right_photo.read()

    # Bodygram only accepts 9:16 portrait photos; crop whatever was uploaded
    # so a normal camera roll image can be used without manual editing.
    normalized_front = normalize_photo(front_bytes)
    normalized_right = normalize_photo(right_bytes)
    if normalized_front:
        front_bytes = normalized_front
    if normalized_right:
        right_bytes = normalized_right

    try:
        result = estimate_measurements(
            front_photo=front_bytes,
            right_photo=right_bytes,
            age=age,
            gender=gender,
            height_cm=height_cm,
            weight_kg=weight_kg,
        )
    except BodygramError as exc:
        return JsonResponse({'error': str(exc)}, status=503)

    session_key = get_session_key(request)
    measurements, _ = UserMeasurement.objects.get_or_create(
        user=request.user if request.user.is_authenticated else None,
        session_key=session_key if not request.user.is_authenticated else ''
    )

    for field, value in result['measurements'].items():
        setattr(measurements, field, value)
    measurements.age = int(age)
    measurements.gender = gender
    measurements.height_cm = height_cm
    measurements.weight_kg = weight_kg
    measurements.unit = 'cm'
    measurements.bodygram_scan_id = result['scan_id']
    measurements.bodygram_measurements = result['all_measurements']
    measurements.body_composition = result['body_composition'] or {}
    measurements.bodygram_posture = result['posture'] or {}
    measurements.bodygram_scanned_at = timezone.now()
    _store_bodygram_files(
        measurements,
        scan_id=result['scan_id'],
        front_bytes=front_bytes,
        right_bytes=right_bytes,
        front_name='front.jpg' if normalized_front else (getattr(front_photo, 'name', '') or ''),
        right_name='right.jpg' if normalized_right else (getattr(right_photo, 'name', '') or ''),
        avatar_bytes=result.get('avatar_obj'),
    )
    measurements.save()

    return JsonResponse({
        'status': 'success',
        'scan_id': result['scan_id'],
        'measurements': result['measurements'],
        'all_measurements': result['all_measurements'],
        'body_composition': result['body_composition'],
        'posture': result['posture'],
        'avatar_url': measurements.bodygram_avatar.url if measurements.bodygram_avatar else '',
        'height_cm': measurements.height_cm or 0,
        'front_photo_url': measurements.bodygram_front_photo.url if measurements.bodygram_front_photo else '',
        'right_photo_url': measurements.bodygram_right_photo.url if measurements.bodygram_right_photo else '',
        'scanned_at': timezone.localtime(measurements.bodygram_scanned_at).strftime('%d %b %Y, %H:%M'),
    })


def _photo_extension(filename, fallback='jpg'):
    suffix = os.path.splitext(filename or '')[1].lower().lstrip('.')
    return suffix if suffix in {'jpg', 'jpeg', 'png'} else fallback


def _replace_file(field_file, name, content):
    if field_file:
        field_file.delete(save=False)
    field_file.save(name, content, save=False)


def _store_shared_file(field_file, name, content):
    """Store a scan artifact once per file name and reuse existing copies.

    Avatar models are ~3 MB and identical for a given scan, so repeated saves
    for the same scan point at the same file instead of duplicating it.
    """
    storage = field_file.storage
    if storage.exists(name):
        if field_file.name != name:
            field_file.name = name
        return
    _replace_file(field_file, name, content)


def _store_bodygram_files(profile, *, scan_id, front_bytes, right_bytes,
                          front_name, right_name, avatar_bytes):
    """Persist the scan artifacts without a second scan or quota use.

    Photos are stored so the profile can show which images produced the scan,
    the `.obj` avatar is stored for the 3D viewer, and both are deletable.
    """
    scan_id = scan_id or 'scan'
    _replace_file(
        profile.bodygram_front_photo,
        f"{scan_id}-front.{_photo_extension(front_name)}",
        ContentFile(front_bytes),
    )
    _replace_file(
        profile.bodygram_right_photo,
        f"{scan_id}-right.{_photo_extension(right_name)}",
        ContentFile(right_bytes),
    )
    if avatar_bytes:
        _store_shared_file(
            profile.bodygram_avatar,
            f"{scan_id}.obj",
            ContentFile(avatar_bytes),
        )


@csrf_exempt
def api_bodygram_delete_photos(request):
    """Remove the stored scan photos from the profile."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    session_key = get_session_key(request)
    measurements, _ = UserMeasurement.objects.get_or_create(
        user=request.user if request.user.is_authenticated else None,
        session_key=session_key if not request.user.is_authenticated else ''
    )

    for field in ('bodygram_front_photo', 'bodygram_right_photo'):
        field_file = getattr(measurements, field)
        if field_file:
            field_file.delete(save=False)
        setattr(measurements, field, '')
    measurements.save(update_fields=['bodygram_front_photo', 'bodygram_right_photo'])

    return JsonResponse({'status': 'deleted'})


@csrf_exempt
def api_toggle_favorite(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = {}

    design_id = data.get('design_id')
    if not design_id:
        return JsonResponse({'error': 'design_id required'}, status=400)

    session_key = get_session_key(request)
    design = get_object_or_404(Design, id=design_id)

    fav = Favorite.objects.filter(
        Q(user=request.user if request.user.is_authenticated else None) &
        (Q(design=design) if request.user.is_authenticated else Q(design=design, session_key=session_key))
    ).first()

    if fav:
        fav.delete()
        is_saved = False
    else:
        Favorite.objects.create(
            user=request.user if request.user.is_authenticated else None,
            session_key=session_key if not request.user.is_authenticated else '',
            design=design
        )
        is_saved = True

    return JsonResponse({'status': 'ok', 'is_saved': is_saved})


@csrf_exempt
def api_save_look(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = {}

    title = data.get('title', 'Virtual Try-On Look')
    image_url = data.get('image_url', '')
    session_key = get_session_key(request)

    SavedLook.objects.create(
        user=request.user if request.user.is_authenticated else None,
        session_key=session_key if not request.user.is_authenticated else '',
        title=title,
        image_url=image_url
    )

    return JsonResponse({'status': 'saved'})


# ---------------------------------------------------------------------------
# Personal wardrobe
# ---------------------------------------------------------------------------

WARDROBE_ALLOWED_TYPES = {'image/jpeg', 'image/jpg', 'image/png', 'image/webp'}
WARDROBE_MAX_BYTES = 12 * 1024 * 1024
WARDROBE_BATCH_SIZE = 6


@csrf_exempt
def api_wardrobe_upload(request):
    """Store one batch of wardrobe photos, normalising each image."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    uploads = request.FILES.getlist('photos')[:WARDROBE_BATCH_SIZE]
    if not uploads:
        return JsonResponse({'error': 'Choose at least one photo to upload.'}, status=400)

    limit = getattr(settings, 'WARDROBE_MAX_ITEMS', 60)
    existing = WardrobeItem.objects.filter(wardrobe_owner_filter(request)).count()
    remaining = max(0, limit - max(existing, 0))
    if not remaining:
        return JsonResponse(
            {'error': f'Your wardrobe is full ({limit} items). Remove a piece to add another.'},
            status=400,
        )

    session_key = get_session_key(request)
    user = request.user if request.user.is_authenticated else None
    created = []
    errors = []

    for upload in uploads:
        if len(created) >= remaining:
            errors.append(f'Only {limit} items fit in a wardrobe right now.')
            break

        content_type = (getattr(upload, 'content_type', '') or '').lower()
        if content_type and content_type not in WARDROBE_ALLOWED_TYPES:
            errors.append(f'{upload.name}: use a JPEG, PNG, or WebP photo.')
            continue
        if upload.size > WARDROBE_MAX_BYTES:
            errors.append(f'{upload.name}: photos must be smaller than 12 MB.')
            continue

        try:
            prepared = prepare_photo(upload.read())
        except WardrobeImageError as exc:
            errors.append(f'{upload.name}: {exc}')
            continue

        item = WardrobeItem(
            user=user,
            session_key=session_key if not user else '',
            name=os.path.splitext(os.path.basename(upload.name or ''))[0][:60].replace('_', ' ').strip(),
        )
        item.image.save(f'{uuid4().hex}.jpg', ContentFile(prepared.full), save=False)
        item.thumb.save(f'{uuid4().hex}-thumb.jpg', ContentFile(prepared.thumb), save=False)
        if prepared.colour:
            item.colours = [prepared.colour]
        item.save()
        created.append(item)

    if not created:
        message = errors[0] if errors else 'None of those photos could be added.'
        return JsonResponse({'error': message}, status=400)

    return JsonResponse({
        'items': [_wardrobe_payload(item) for item in created],
        'errors': errors,
    })


@csrf_exempt
def api_wardrobe_tag(request, item_id):
    """Let the fashion AI read one item once and store its tags."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    item = _wardrobe_item_for(request, item_id)
    if item.tagged:
        return JsonResponse({'item': _wardrobe_payload(item)})

    try:
        with item.image.open('rb') as handle:
            data = handle.read()
    except OSError:
        return JsonResponse({'error': 'That wardrobe photo is missing. Upload it again.'}, status=400)

    try:
        tags = tag_wardrobe_image(data, 'image/jpeg', item.name)
    except GeminiError as exc:
        return JsonResponse({'error': str(exc), 'fallback': True}, status=503)

    item.name = tags['name'] or item.name
    item.category = tags['category']
    if tags['colours']:
        item.colours = tags['colours']
    item.pattern = tags['pattern']
    item.formality = tags['formality']
    item.seasons = tags['seasons']
    item.style_tags = tags['style_tags']
    item.tagged = True
    item.save()
    return JsonResponse({'item': _wardrobe_payload(item)})


@csrf_exempt
def api_wardrobe_update(request, item_id):
    """Let the user correct the AI's name, category, or notes."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    item = _wardrobe_item_for(request, item_id)
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    if 'name' in data:
        item.name = ' '.join(str(data.get('name') or '').split())[:120]
    if 'category' in data:
        valid = {choice for choice, _ in WardrobeItem.CATEGORY_CHOICES}
        if data['category'] in valid:
            item.category = data['category']
    if 'formality' in data:
        valid = {choice for choice, _ in WardrobeItem.FORMALITY_CHOICES}
        item.formality = data['formality'] if data['formality'] in valid else ''
    if 'notes' in data:
        item.notes = str(data.get('notes') or '').strip()[:500]
    item.save()
    return JsonResponse({'item': _wardrobe_payload(item)})


@csrf_exempt
def api_wardrobe_delete(request, item_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    item = _wardrobe_item_for(request, item_id)
    for field in ('image', 'thumb'):
        file_field = getattr(item, field)
        if not file_field:
            continue
        try:
            file_field.delete(save=False)
        except OSError as exc:
            # Windows can hold a short-lived lock while another request streams
            # the photo. The row still goes away; log the orphaned file instead
            # of failing the whole delete.
            logger.warning('Could not remove wardrobe %s for item %s: %s', field, item_id, exc)
    item.delete()
    return JsonResponse({'status': 'deleted'})


@csrf_exempt
def api_wardrobe_worn(request):
    """Record that a chosen set of pieces was actually worn."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    ids = data.get('item_ids') or []
    if not isinstance(ids, list) or not ids:
        return JsonResponse({'error': 'Choose at least one piece.'}, status=400)

    items = list(
        WardrobeItem.objects.filter(wardrobe_owner_filter(request), id__in=ids[:12])
    )
    now = timezone.now()
    for item in items:
        item.wear_count += 1
        item.last_worn = now
    WardrobeItem.objects.bulk_update(items, ['wear_count', 'last_worn'])
    return JsonResponse({'status': 'ok', 'updated': len(items)})


@csrf_exempt
def api_wardrobe_recommend(request):
    """Build outfit ideas from the user's own wardrobe."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        data = {}

    items = list(WardrobeItem.objects.filter(wardrobe_owner_filter(request))[:60])
    if len(items) < 2:
        return JsonResponse(
            {'error': 'Add at least two pieces — a top and a bottom, or a dress — first.'},
            status=400,
        )

    measurements = UserMeasurement.objects.filter(wardrobe_owner_filter(request)).first()
    profile = {}
    if measurements:
        profile = {
            'gender': measurements.gender,
            'height_cm': measurements.height_cm,
            'chest_cm': measurements.chest,
            'waist_cm': measurements.waist,
            'hips_cm': measurements.hips,
        }

    catalog = []
    for item in items:
        catalog.append({
            'id': item.id,
            'name': item.name or 'Untitled piece',
            'category': item.category,
            'colours': item.colours or [],
            'pattern': item.pattern,
            'formality': item.formality,
            'seasons': item.seasons or [],
            'style_tags': item.style_tags or [],
            'wear_count': item.wear_count,
        })

    try:
        outfits = recommend_wardrobe_outfits(
            items=catalog,
            occasion=str(data.get('occasion') or '').strip()[:60],
            weather=str(data.get('weather') or '').strip()[:80],
            note=str(data.get('note') or '').strip()[:300],
            profile=profile,
        )
    except GeminiError as exc:
        return JsonResponse({'error': str(exc)}, status=503)

    by_id = {str(item.id): item for item in items}
    resolved = []
    for outfit in outfits:
        pieces = [by_id[item_id] for item_id in outfit['item_ids'] if item_id in by_id]
        if not pieces:
            continue
        resolved.append({
            'title': outfit['title'],
            'why': outfit['why'],
            'tip': outfit['tip'],
            'items': [_wardrobe_payload(piece) for piece in pieces],
        })

    if not resolved:
        return JsonResponse(
            {'error': 'The fashion AI did not return a usable outfit. Try again.'},
            status=503,
        )
    return JsonResponse({'outfits': resolved})


def wardrobe_item_photo(request, item_id):
    return _wardrobe_file_response(request, item_id, 'image')


def wardrobe_item_thumb(request, item_id):
    return _wardrobe_file_response(request, item_id, 'thumb')


def _wardrobe_file_response(request, item_id, field):
    item = _wardrobe_item_for(request, item_id)
    file_field = getattr(item, field)
    if not file_field:
        raise Http404('Photo not found')
    try:
        handle = file_field.open('rb')
    except OSError as exc:
        raise Http404('Photo not found') from exc
    response = FileResponse(handle, content_type='image/jpeg')
    response['Cache-Control'] = 'private, max-age=3600'
    return response
