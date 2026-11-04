import json
import logging
import os

from django.core.files.base import ContentFile
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
from .models import Category, Design, UserMeasurement, SavedLook, Favorite, VirtualTryOn
from .services.fashn_vton import FashnVtonError, generate_try_on
from .services.gemini_ai import GeminiError, generate_stylist_response, generate_try_on as generate_gemini_try_on
from .services.bodygram import BodygramError, estimate_measurements, normalize_photo

logger = logging.getLogger(__name__)


class TryOnError(Exception):
    """Raised when no configured provider can render a try-on."""


def get_session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _generate_try_on(*, person_image, garment_image, category, garment_photo_type):
    """Render a try-on, falling back from Gemini to FASHN VTON.

    Returns a ``(result_url, provider)`` tuple. Gemini is only attempted when it
    is the configured provider and an API key is present; any Gemini failure is
    logged and retried once through the FASHN Space.
    """
    provider = getattr(settings, 'AI_PROVIDER', 'gemini')
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
            logger.warning("Gemini try-on failed, falling back to FASHN VTON: %s", exc)
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
        logger.warning("FASHN VTON try-on failed: %s", exc)
        failures.append(f"FASHN VTON: {exc}")

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
    return render(request, 'wardrobe.html', {
        'saved_looks': saved_looks,
        'favorites': favorites,
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
        advice = "Here is a hand-picked recommendation that balances contemporary fit with rich texture. You can preview this look on a model using FASHN VTON 1.5 in the fitting studio on the right!"
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
