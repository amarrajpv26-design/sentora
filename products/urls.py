from django.urls import path
from . import views

urlpatterns = [
    path('admin/categories/', views.admin_category_list, name='admin_category_list'),
    path('admin/categories/add/', views.add_category, name='add_category'),
    path('admin/categories/edit/<int:category_id>/', views.edit_category, name='edit_category'),
    path('admin/categories/toggle/<int:category_id>/', views.toggle_category_status, name='toggle_category_status'),
]