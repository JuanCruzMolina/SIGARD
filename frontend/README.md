# Frontend de SIGARD

SPA React/Vite con dos dominios visuales explícitamente separados:

- vigilancia epidemiológica experimental: `/`, `/mapa`, `/validacion` y
  `/metodologia`;
- prevención y servicios ciudadanos: `/prevencion`;
- operación privada de reportes: `/admin/reportes`.

## Desarrollo

```bash
npm install
npm run dev
```

Copiar `.env.example` a `.env` y configurar `VITE_API_URL`. Para producción, la
SPA puede desplegarse en Vercel y debe apuntar a una API FastAPI servida por
HTTPS. Los datos sanitarios estáticos se cargan desde `public/data/` y se
validan antes de mostrarse. El directorio contiene 24 CAPS públicos y 3
hospitales de referencia; 23 CAPS conservan `vigencia_por_confirmar`, por lo que
no deben interpretarse como atención disponible en tiempo real.

## Verificación

```bash
npm run lint
npm run build
```

Ambas órdenes finalizaron correctamente en la verificación de cierre. No se
pudieron ejecutar pruebas visuales, responsive, de teclado ni de lector de
pantalla asistidas por navegador porque el entorno no dispone de uno instalado;
son comprobaciones pendientes antes de publicar.

El formulario nunca solicita identificadores directos. La geolocalización sólo
se activa al pulsar el botón correspondiente y los reportes no se representan
en el mapa epidemiológico. La búsqueda opcional requiere un consentimiento
separado y envía la referencia a la API de SIGARD, que actúa como intermediaria
ante Nominatim/OpenStreetMap sin reenviar la IP del navegador. Si la persona no
quiere compartir esa referencia puede ubicar el marcador manualmente.
