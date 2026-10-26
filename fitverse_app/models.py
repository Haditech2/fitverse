from django.db import models
from django.contrib.auth.models import User

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Design(models.Model):
    VTON_CATEGORY_CHOICES = [
        ('one-pieces', 'One-Pieces & Sets (Senator / Gown)'),
        ('tops', 'Tops & Shirts'),
        ('bottoms', 'Trousers & Skirts'),
    ]

    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='designs')
    price = models.IntegerField(default=0, help_text="Price in NGN (0 for inspiration items)")
    price_label = models.CharField(max_length=50, default="₦0")
    fabric = models.CharField(max_length=150, blank=True)
    silhouette = models.CharField(max_length=100, blank=True)
    image_url = models.URLField(max_length=500)
    source_link = models.URLField(max_length=500, blank=True)
    source_label = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    styling_advice = models.TextField(blank=True)
    search_keywords = models.TextField(blank=True, help_text="Keywords for filtering")
    vton_category = models.CharField(max_length=20, choices=VTON_CATEGORY_CHOICES, default='one-pieces')
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_featured', '-created_at']

    def __str__(self):
        return self.title


class UserMeasurement(models.Model):
    UNIT_CHOICES = [
        ('cm', 'Centimeters'),
        ('in', 'Inches'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='measurements')
    session_key = models.CharField(max_length=100, blank=True, db_index=True)
    unit = models.CharField(max_length=5, choices=UNIT_CHOICES, default='cm')
    chest = models.FloatField(default=96.0)
    waist = models.FloatField(default=82.0)
    hips = models.FloatField(default=100.0)
    shoulder = models.FloatField(default=46.0)
    sleeve = models.FloatField(default=64.0)
    inseam = models.FloatField(default=81.0)
    neck = models.FloatField(default=39.0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        owner = self.user.username if self.user else f"Session {self.session_key[:8]}"
        return f"Measurements ({owner})"


class SavedLook(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='saved_looks')
    session_key = models.CharField(max_length=100, blank=True, db_index=True)
    title = models.CharField(max_length=200, default="Virtual Try-On Look")
    image_url = models.TextField()
    design = models.ForeignKey(Design, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='favorites')
    session_key = models.CharField(max_length=100, blank=True, db_index=True)
    design = models.ForeignKey(Design, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'design')

    def __str__(self):
        return f"Favorite: {self.design.title}"


class VirtualTryOn(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing (FASHN VTON 1.5)'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    session_key = models.CharField(max_length=100, blank=True)
    design = models.ForeignKey(Design, on_delete=models.SET_NULL, null=True, blank=True)
    model_preset = models.CharField(max_length=50, default='male-1')
    user_photo_url = models.URLField(max_length=500, blank=True)
    result_photo_url = models.URLField(max_length=500, blank=True)
    category = models.CharField(max_length=20, default='one-pieces')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"TryOn #{self.id} - {self.status}"
