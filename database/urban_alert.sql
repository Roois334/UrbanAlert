-- ============================================================
--  URBAN ALERT — Base de datos v3.0 LIMPIA
--  Importar: mysql -u root -p < urban_alert.sql
--
--  CREDENCIALES DE ACCESO:
--  ┌─────────────────┬─────────────────────────┬────────────────┐
--  │  Rol            │  Email                  │  Contraseña    │
--  ├─────────────────┼─────────────────────────┼────────────────┤
--  │  Super Admin    │  superadmin@yopmail.com │ superadmin2026 │
--  │  Administrador  │  admin@yopmail.com      │ admin2026      │
--  │  Técnico 1      │  tecnico1@yopmail.com   │ tecnico2026    │
--  │  Técnico 2      │  tecnico2@yopmail.com   │ tecnico2026    │
--  │  Técnico 3      │  tecnico3@yopmail.com   │ tecnico2026    │
--  │  Técnico 4      │  tecnico4@yopmail.com   │ tecnico2026    │
--  │  Técnico 5      │  tecnico5@yopmail.com   │ tecnico2026    │
--  │  Ciudadano 1    │  ciudadano1@yopmail.com │ ciudad2026     │
--  │  Ciudadano 2    │  ciudadano2@yopmail.com │ ciudad2026     │
--  │  Ciudadano 3    │  ciudadano3@yopmail.com │ ciudad2026     │
--  │  Ciudadano 4    │  ciudadano4@yopmail.com │ ciudad2026     │
--  │  Ciudadano 5    │  ciudadano5@yopmail.com │ ciudad2026     │
--  └─────────────────┴─────────────────────────┴────────────────┘
-- ============================================================

DROP DATABASE IF EXISTS urban_alert;
CREATE DATABASE urban_alert CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE urban_alert;

-- ─── ROLES ───────────────────────────────────────────────────
CREATE TABLE roles (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    nombre      VARCHAR(50) NOT NULL UNIQUE,
    descripcion TEXT,
    creado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO roles (nombre, descripcion) VALUES
('visitante',     'Acceso público sin cuenta'),
('ciudadano',     'Puede crear reportes y hacer seguimiento'),
('tecnico',       'Recibe asignaciones y resuelve reportes'),
('administrador', 'Gestiona plataforma, usuarios y asignaciones'),
('super_admin',   'Control total del sistema');

-- ─── USUARIOS ────────────────────────────────────────────────
-- IMPORTANTE: Las contraseñas usan werkzeug scrypt.
-- El app.py regenera los hashes al arrancar si son inválidos.
-- Para NUEVA BD usa directamente esta importación.
CREATE TABLE usuarios (
    id               INT PRIMARY KEY AUTO_INCREMENT,
    nombre           VARCHAR(100) NOT NULL,
    apellido         VARCHAR(100),
    email            VARCHAR(150) NOT NULL UNIQUE,
    password_hash    VARCHAR(255) NOT NULL,
    telefono         VARCHAR(20),
    ciudad           ENUM('Facatativá','Madrid','Mosquera') DEFAULT 'Facatativá',
    rol_id           INT NOT NULL DEFAULT 2,
    activo           BOOLEAN DEFAULT TRUE,
    email_verificado BOOLEAN DEFAULT TRUE,
    ultimo_login     TIMESTAMP NULL,
    creado_en        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (rol_id) REFERENCES roles(id)
);

-- Contraseña: superadmin2026
INSERT INTO usuarios (nombre, apellido, email, password_hash, telefono, ciudad, rol_id, activo, email_verificado) VALUES
('Super', 'Admin', 'superadmin@yopmail.com',
 'scrypt:32768:8:1$pLqdChj0itj3wFxZ$48307bd76a2846480ab1d0d6c2a3257baf1375300575be005aed41af2059efe56367e433a50831029826c580e9259f1f1777440699602a55f915d95ba2f34f81',
 '3000000000', 'Facatativá', 5, TRUE, TRUE);

-- Contraseña: admin2026
INSERT INTO usuarios (nombre, apellido, email, password_hash, telefono, ciudad, rol_id, activo, email_verificado) VALUES
('Carlos', 'Gómez Restrepo', 'admin@yopmail.com',
 'scrypt:32768:8:1$CxAUZ5Aoz5tfazWd$9bac765d591b95e47a7ffe1e5dbebfd6a400e8322c78b03539ae0191e53c2c4aabb486bcde00f7d7e6f67f022f261aa02077210b6ccb2a0deb864d5901fd15ca',
 '3109876543', 'Facatativá', 4, TRUE, TRUE);

-- Contraseña: tecnico2026 (5 técnicos)
INSERT INTO usuarios (nombre, apellido, email, password_hash, telefono, ciudad, rol_id, activo, email_verificado) VALUES
('Luis',   'Martínez Ríos',   'tecnico1@yopmail.com',
 'scrypt:32768:8:1$ICyHX9fk4MzBUpPn$8adbb9f7d6d423b2bb455bfb066cbb578815f35df57279d5cb9f8f0b8194d196242debe4ff054ca6ae48bac784c1bd22153aa83db5491a67f7d06a23f0e5dad0',
 '3201112233', 'Facatativá', 3, TRUE, TRUE),
('Ana',    'Torres Quintero', 'tecnico2@yopmail.com',
 'scrypt:32768:8:1$bnZsFCllbZ7cAl88$443c220727fd5272034a5d2b921076f183041076dde8fdacec88ef15ea12affa72cadc5ce7f2b12aeb1474fccc4dd7e13c0b1dc5ffe444657d57be50ba5c9359',
 '3154445566', 'Mosquera', 3, TRUE, TRUE),
('Pedro',  'Silva Ospina',    'tecnico3@yopmail.com',
 'scrypt:32768:8:1$I2k1AQASXKZ9ykFt$36cf5e0dd7467e37391bca6c0d08ab86b8bf35335e4bd8d084a5e50bf4d4481fbd00f35647176797d2d09f3eb4cd05499c45c5f840c177b48afbcaec5281cd6e',
 '3178889900', 'Madrid', 3, TRUE, TRUE),
('Camila', 'Rincón Vargas',   'tecnico4@yopmail.com',
 'scrypt:32768:8:1$cidKCED3EEMDLdfw$52d27a49ce74bf50d6ac47f8398b8f5310ccdd7a6729062afbc67ddae15f2d91261539df087e3e8fc106bd1c25d086ffabb4bbcff874a0debe7bf4eaa435dbc0',
 '3132224455', 'Facatativá', 3, TRUE, TRUE),
('Andrés', 'Pérez Suárez',    'tecnico5@yopmail.com',
 'scrypt:32768:8:1$Pc3TiOpVXAvCfyhJ$ed9ce54fa2e40b88e4c14c20494555cfb859aaf94cc18d03c5891034555abf958a7f3d7a3ba511fcb5538c74d49128e6d20ee948f4ac2d9169c6e3b62d84bbe5',
 '3168880011', 'Madrid', 3, TRUE, TRUE);

-- Contraseña: ciudad2026 (5 ciudadanos)
INSERT INTO usuarios (nombre, apellido, email, password_hash, telefono, ciudad, rol_id, activo, email_verificado) VALUES
('María',     'López Pineda',   'ciudadano1@yopmail.com',
 'scrypt:32768:8:1$kVKDchpIh4LALArc$c08c25bf20c2da384c1e3af8e29bd251c0406c55b836c859b9b4bfe94472d4ae06ed9ebc463c4519c37bae379b5df7cf7daead3f513595f7902dd8fe177b8a9c',
 '3007778899', 'Facatativá', 2, TRUE, TRUE),
('Jorge',     'Ramírez Acosta', 'ciudadano2@yopmail.com',
 'scrypt:32768:8:1$tjqMP8QnRuWgxVks$655c911f5cc0b4eb30204ee792bd01238d4d20a42b3aeeb1388b964eb17a19024a6a71a5c213ea9b5e9963ca7174e2351994441e23a146b409b7e840d3899854',
 '3123334455', 'Madrid', 2, TRUE, TRUE),
('Patricia',  'Herrera Nieto',  'ciudadano3@yopmail.com',
 'scrypt:32768:8:1$6NOV9B0t8f2PQX1C$5e64bd5956402a2412a373344a12a1004ec19d94db41ebdfe214c8eb3df711d19d6e90c959fe6796262f58d62dd1b8bc7424a66494af82040fb169b86854b9f1',
 '3056667788', 'Mosquera', 2, TRUE, TRUE),
('Valentina', 'Cruz Bermúdez',  'ciudadano4@yopmail.com',
 'scrypt:32768:8:1$cTQSECOq3aIaYqge$5306bceef4a627b0f6ad894aef1a61b70976cb5d12d0d337f66091e55571ee52df5b3447dcc64958eb30bc05fa976e54b2fb6d2d335e3bfa04a6408e1b3c9d31',
 '3011115566', 'Facatativá', 2, TRUE, TRUE),
('Santiago',  'Moreno Ávila',   'ciudadano5@yopmail.com',
 'scrypt:32768:8:1$Ok8wbNXlExEcVv1b$68cbcab365cff56dffab5e005ce37fa2fc1da78b26ba0b982e317b9819d05301269cd4b13b96b23b488bb05bdd1b77ebb7934b896b38731ed26f989f22b350a2',
 '3167774455', 'Madrid', 2, TRUE, TRUE);

-- ─── CATEGORÍAS ──────────────────────────────────────────────
CREATE TABLE categorias (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    nombre      VARCHAR(100) NOT NULL,
    descripcion TEXT,
    icono       VARCHAR(50),
    color       VARCHAR(7) DEFAULT '#FF6B00',
    activa      BOOLEAN DEFAULT TRUE
);

INSERT INTO categorias (nombre, descripcion, icono, color) VALUES
('Bache / Pavimento',  'Huecos, grietas, hundimientos o daños en la vía',               'road',      '#E74C3C'),
('Basura / Residuos',  'Acumulación de basura, escombros o depósito ilegal',             'trash',     '#F39C12'),
('Espacio Público',    'Daños en andenes, parques, mobiliario urbano',                   'building',  '#9B59B6'),
('Señalización Vial',  'Señales dañadas, faltantes o semáforos en mal estado',          'signpost',  '#E67E22'),
('Alumbrado Público',  'Postes o luminarias apagados, dañados o peligrosos',            'lightbulb', '#F1C40F'),
('Árbol / Vegetación', 'Árboles caídos, ramas peligrosas o vegetación que obstruye',   'tree',      '#27AE60'),
('Inundación',         'Encharcamiento, desbordamiento de canales o drenajes tapados',  'droplets',  '#2980B9'),
('Otro',               'Situaciones que no encajan en otras categorías',                 'flag',      '#7F8C8D');

-- ─── REPORTES ────────────────────────────────────────────────
CREATE TABLE reportes (
    id               INT PRIMARY KEY AUTO_INCREMENT,
    titulo           VARCHAR(200) NOT NULL,
    descripcion      TEXT,
    categoria_id     INT NOT NULL,
    ciudad           ENUM('Facatativá','Madrid','Mosquera') NOT NULL,
    direccion        VARCHAR(300),
    latitud          DECIMAL(10,8),
    longitud         DECIMAL(11,8),
    estado           ENUM('pendiente','en_revision','aprobado','asignado',
                          'en_progreso','resuelto','rechazado','duplicado') DEFAULT 'pendiente',
    prioridad        ENUM('baja','media','alta','critica') DEFAULT 'media',
    gravedad_ia      DECIMAL(5,2),
    usuario_id       INT,
    tecnico_id       INT,
    admin_id         INT,
    imagen_principal VARCHAR(255),
    imagen_hash      VARCHAR(16) NULL,
    analisis_ia      JSON,
    es_duplicado     BOOLEAN DEFAULT FALSE,
    votos            INT DEFAULT 0,
    vistas           INT DEFAULT 0,
    publico          BOOLEAN DEFAULT TRUE,
    fecha_asignacion TIMESTAMP NULL,
    fecha_resolucion TIMESTAMP NULL,
    creado_en        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (categoria_id) REFERENCES categorias(id),
    FOREIGN KEY (usuario_id)   REFERENCES usuarios(id),
    FOREIGN KEY (tecnico_id)   REFERENCES usuarios(id),
    FOREIGN KEY (admin_id)     REFERENCES usuarios(id)
);

-- (sin reportes de ejemplo — base limpia)

-- ─── EVIDENCIAS ──────────────────────────────────────────────
CREATE TABLE evidencias (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    reporte_id  INT NOT NULL,
    usuario_id  INT NOT NULL,
    tipo        ENUM('imagen','video','documento') DEFAULT 'imagen',
    archivo     VARCHAR(255) NOT NULL,
    descripcion TEXT,
    subido_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reporte_id) REFERENCES reportes(id) ON DELETE CASCADE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

-- ─── TÉCNICOS ────────────────────────────────────────────────
CREATE TABLE tecnicos (
    id                 INT PRIMARY KEY AUTO_INCREMENT,
    usuario_id         INT NOT NULL UNIQUE,
    especialidad       VARCHAR(150),
    zona_cobertura     ENUM('Facatativá','Madrid','Mosquera','Todas') DEFAULT 'Todas',
    disponible         BOOLEAN DEFAULT TRUE,
    reportes_activos   INT DEFAULT 0,
    reportes_resueltos INT DEFAULT 0,
    calificacion       DECIMAL(3,2) DEFAULT 5.0,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

INSERT INTO tecnicos (usuario_id, especialidad, zona_cobertura, disponible, reportes_activos, reportes_resueltos, calificacion) VALUES
(3, 'Infraestructura vial: pavimentación, bacheo y señalización', 'Facatativá', TRUE, 2, 28, 4.9),
(4, 'Espacio público: arbolado urbano, andenes y mobiliario',     'Mosquera',   TRUE, 3, 19, 4.7),
(5, 'Redes de servicios: alcantarillado, drenaje e iluminación',  'Madrid',     TRUE, 2, 14, 4.8),
(6, 'Mantenimiento general: limpieza, residuos y andenes',        'Facatativá', TRUE, 1,  9, 4.6),
(7, 'Señalización vial y control de tráfico',                     'Madrid',     TRUE, 1,  5, 4.5);

-- ─── HISTORIAL ───────────────────────────────────────────────
CREATE TABLE historial (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    reporte_id      INT NOT NULL,
    usuario_id      INT,
    accion          VARCHAR(100) NOT NULL,
    descripcion     TEXT,
    estado_anterior VARCHAR(50),
    estado_nuevo    VARCHAR(50),
    creado_en       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reporte_id) REFERENCES reportes(id) ON DELETE CASCADE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

-- (sin historial de ejemplo)

-- ─── NOTIFICACIONES ──────────────────────────────────────────
CREATE TABLE notificaciones (
    id         INT PRIMARY KEY AUTO_INCREMENT,
    usuario_id INT NOT NULL,
    titulo     VARCHAR(200) NOT NULL,
    mensaje    TEXT NOT NULL,
    tipo       ENUM('info','exito','advertencia','error') DEFAULT 'info',
    leida      BOOLEAN DEFAULT FALSE,
    reporte_id INT,
    creado_en  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
    FOREIGN KEY (reporte_id) REFERENCES reportes(id) ON DELETE SET NULL
);

-- (sin notificaciones de ejemplo)

-- ─── ÍNDICES ─────────────────────────────────────────────────
CREATE INDEX idx_reportes_ciudad    ON reportes(ciudad);
CREATE INDEX idx_reportes_estado    ON reportes(estado);
CREATE INDEX idx_reportes_coords    ON reportes(latitud, longitud);
CREATE INDEX idx_notif_usuario      ON notificaciones(usuario_id, leida);
CREATE INDEX idx_usuarios_email     ON usuarios(email);
CREATE INDEX idx_historial_reporte  ON historial(reporte_id);
CREATE INDEX idx_reportes_prioridad ON reportes(prioridad, estado);

-- ─── VERIFICACIÓN FINAL ───────────────────────────────────────
SELECT '=== URBAN ALERT BD IMPORTADA CORRECTAMENTE ===' AS resultado;
SELECT 'roles'          AS tabla, COUNT(*) AS registros FROM roles
UNION ALL SELECT 'usuarios',       COUNT(*) FROM usuarios
UNION ALL SELECT 'categorias',     COUNT(*) FROM categorias
UNION ALL SELECT 'reportes',       COUNT(*) FROM reportes
UNION ALL SELECT 'tecnicos',       COUNT(*) FROM tecnicos
UNION ALL SELECT 'historial',      COUNT(*) FROM historial
UNION ALL SELECT 'notificaciones', COUNT(*) FROM notificaciones;

SELECT '=== USUARIOS CREADOS ===' AS info;
SELECT u.id, CONCAT(u.nombre, ' ', IFNULL(u.apellido,'')) AS nombre,
       u.email, r.nombre AS rol
FROM usuarios u JOIN roles r ON u.rol_id = r.id
ORDER BY r.id DESC, u.id;
