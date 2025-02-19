from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import aumentar_stock
from .views import ver_historial_stock

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('registro/', views.registro, name='registro'),
    path('login/', auth_views.LoginView.as_view(template_name='farmacia/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('inventario/', views.ver_inventario, name='ver_inventario'),
    path('mis_pedidos/', views.mis_pedidos, name='mis_pedidos'),
    path('medicamentos/', views.listar_medicamentos, name='listar_medicamentos'),
    path('pedido/<int:medicamento_id>/', views.realizar_pedido, name='realizar_pedido'),
     path('transferencias/gestionar/', views.gestionar_transferencias, name='gestionar_transferencias'),
     path('transferencias/manual/', views.transferencias_manual, name='transferencias_manual'),
    path('transferencias/historial/', views.historial_transferencias, name='historial_transferencias'),
     path('clientes/', views.gestionar_clientes_pedidos, name='gestionar_clientes_pedidos'),
    path('inventario/aumentar/<int:inventario_id>/', aumentar_stock, name='aumentar_stock'),
    path('inventario/historial/', ver_historial_stock, name='historial_stock'),  # ✅ Agregamos la ruta

]

