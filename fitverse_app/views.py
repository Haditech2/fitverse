import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db.models import Q
from .models import Category, Design, UserMeasurement, SavedLook, Favorite, VirtualTryOn
from .services.fashn_vton import FashnVtonError, generate_try_on

def get_session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key

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
    return render(request, 'measurements.html', {
        'measurements': measurements,
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
        result_image = generate_try_on(
            person_image=person_image,
            garment_image=garment_image,
            category=category,
            garment_photo_type=request.POST.get('garment_photo_type', 'model'),
            num_timesteps=30,
            guidance_scale=1.5,
            seed=42,
            segmentation_free=True,
        )
    except FashnVtonError as exc:
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
