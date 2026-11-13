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
    path('studio/', views.studio_view, name='studio'),
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
    path('api/stylist/design/', views.api_stylist_design, name='api_stylist_design'),
    path('api/vton/tryon/', views.api_vton_tryon, name='api_vton_tryon'),
    path('api/measurements/save/', views.api_save_measurements, name='api_save_measurements'),
    path('api/measurements/bodygram/', views.api_bodygram_measurements, name='api_bodygram_measurements'),
    path('api/measurements/bodygram/photos/delete/', views.api_bodygram_delete_photos, name='api_bodygram_delete_photos'),
    path('api/favorite/toggle/', views.api_toggle_favorite, name='api_toggle_favorite'),
    path('api/looks/save/', views.api_save_look, name='api_save_look'),
    path('api/look360/designs/<slug:slug>/', views.api_look360, name='api_look360'),

    # Personal wardrobe
    path('api/wardrobe/upload/', views.api_wardrobe_upload, name='api_wardrobe_upload'),
    path('api/wardrobe/items/<int:item_id>/tag/', views.api_wardrobe_tag, name='api_wardrobe_tag'),
    path('api/wardrobe/items/<int:item_id>/update/', views.api_wardrobe_update, name='api_wardrobe_update'),
    path('api/wardrobe/items/<int:item_id>/delete/', views.api_wardrobe_delete, name='api_wardrobe_delete'),
    path('api/wardrobe/recommend/', views.api_wardrobe_recommend, name='api_wardrobe_recommend'),
    path('api/wardrobe/worn/', views.api_wardrobe_worn, name='api_wardrobe_worn'),
    path('wardrobe/items/<int:item_id>/photo/', views.wardrobe_item_photo, name='wardrobe_item_photo'),
    path('wardrobe/items/<int:item_id>/thumb/', views.wardrobe_item_thumb, name='wardrobe_item_thumb'),
]
