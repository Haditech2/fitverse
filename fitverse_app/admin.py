from django.contrib import admin
from .models import Category, Design, UserMeasurement, SavedLook, Favorite, VirtualTryOn

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Design)
class DesignAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'price_label', 'fabric', 'vton_category', 'is_featured')
    list_filter = ('category', 'vton_category', 'is_featured')
    search_fields = ('title', 'description', 'fabric', 'search_keywords')
    prepopulated_fields = {'slug': ('title',)}

@admin.register(UserMeasurement)
class UserMeasurementAdmin(admin.ModelAdmin):
    list_display = ('user', 'unit', 'chest', 'waist', 'hips', 'updated_at')

@admin.register(SavedLook)
class SavedLookAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'created_at')

@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'design', 'created_at')

@admin.register(VirtualTryOn)
class VirtualTryOnAdmin(admin.ModelAdmin):
    list_display = ('id', 'design', 'category', 'status', 'created_at')
