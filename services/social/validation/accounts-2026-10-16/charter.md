# Alcance E2E

Autorización: añadir BullTheoryio, BitcoinArchive, WatcherGuru y CredibleCrypto, administrar cuentas y verificar la ingesta completa. Análisis de videos pausado por instrucción posterior del usuario.

Superficies: login real del panel, alta y edición del catálogo, validación de perfil mediante twitterapi.io, cron/worker, persistencia JSON, publicación pública y filtros/modal de Urania a 390 y 1280 px.

Escrituras reales: esas cuatro cuentas y sus categorías, catálogo, auditoría, estado de ingesta y JSON del Feed. Credenciales solo desde archivos privados conocidos; ningún valor se imprime ni se conserva en evidencias. Los tests unitarios de baja, errores, concurrencia y cuotas usan directorios temporales y proveedor simulado.

Salida: cuatro ventanas terminadas, autor e ID fijados, texto exacto en modal, enlaces canónicos, estado público coherente, reintento sin nuevas consultas cuando no corresponde. Sin análisis de modelos ni recargas. La evidencia se limita a estas superficies; no certifica estabilidad de siete días, cobertura absoluta de X ni ausencia general de problemas en otros módulos.

Navegador: una ejecución acotada a 180 segundos; pruebas funcionales con timeout de 120 segundos.
