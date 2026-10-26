from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('designs/', views.designs_view, name='designs'),
    path('designs/<slug:slug>/', views.design_detail_view, name='design_detail'),
    path('tryon/', views.tryon_view, name='tryon'),
    path('measurements/', views.measurements_view, name='measurements'),
    path('style-intelligence/', views.style_intelligence_view, name='style_intelligence'),
    path('wardrobe/', views.wardrobe_view, name='wardrobe'),
    path('profile/', views.profile_view, name='profile'),
    path('sources/', views.image_sources_view, name='image_sources'),

    # Auth
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),

    # API Endpoints
    path('api/stylist/chat/', views.api_stylist_chat, name='api_stylist_chat'),
    path('api/vton/tryon/', views.api_vton_tryon, name='api_vton_tryon'),
    path('api/measurements/save/', views.api_save_measurements, name='api_save_measurements'),
    path('api/favorite/toggle/', views.api_toggle_favorite, name='api_toggle_favorite'),
    path('api/looks/save/', views.api_save_look, name='api_save_look'),
]
