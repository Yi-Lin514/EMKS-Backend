-- ============================================================
-- 企業內部知識管理系統 (EMKS) - 資料庫建置腳本
-- Database: AI_G2_DB
-- MySQL Version: 8.0+
-- 執行方式: mysql -u root -p < EMKS_DB.sql
-- ============================================================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

DROP DATABASE IF EXISTS AI_G2_DB;

CREATE DATABASE AI_G2_DB
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE AI_G2_DB;

-- ============================================================
-- 會員與權限管理
-- ============================================================

-- 部門表
CREATE TABLE departments (
    id INT PRIMARY KEY AUTO_INCREMENT,
    code VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT NULL,
    parent_id INT NULL,
    manager_id INT NULL,
    level TINYINT NOT NULL DEFAULT 1,
    sort_order INT DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code (code),
    INDEX idx_parent_id (parent_id),
    INDEX idx_manager_id (manager_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 角色表
CREATE TABLE roles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT NULL,
    is_system BOOLEAN DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 權限表
CREATE TABLE permissions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    code VARCHAR(100) NOT NULL,
    name VARCHAR(100) NOT NULL,
    resource VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,
    description TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code (code),
    INDEX idx_resource (resource)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 使用者表
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    employee_id VARCHAR(20) NULL,
    email VARCHAR(255) NOT NULL,
    password_hash CHAR(60) NOT NULL,
    name VARCHAR(100) NOT NULL,
    avatar_url VARCHAR(500) NULL,
    department_id INT NULL,
    job_title VARCHAR(100) NULL,
    phone VARCHAR(20) NULL,
    status ENUM('active', 'inactive', 'suspended') NOT NULL DEFAULT 'active',
    failed_login_count TINYINT NOT NULL DEFAULT 0,
    locked_until DATETIME NULL,
    last_login_at DATETIME NULL,
    last_login_ip VARCHAR(45) NULL,
    password_changed_at DATETIME NULL,
    created_by INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_employee_id (employee_id),
    UNIQUE KEY uk_email (email),
    INDEX idx_department_id (department_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 外鍵（解決循環依賴）
ALTER TABLE departments
    ADD CONSTRAINT fk_dept_parent FOREIGN KEY (parent_id) REFERENCES departments(id) ON DELETE SET NULL,
    ADD CONSTRAINT fk_dept_manager FOREIGN KEY (manager_id) REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE users
    ADD CONSTRAINT fk_user_dept FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL,
    ADD CONSTRAINT fk_user_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL;

-- 角色權限關聯表
CREATE TABLE role_permissions (
    role_id INT NOT NULL,
    permission_id INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (role_id, permission_id),
    CONSTRAINT fk_rp_role FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    CONSTRAINT fk_rp_permission FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 使用者角色關聯表
CREATE TABLE user_roles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    role_id INT NOT NULL,
    scope_type ENUM('global', 'department') NOT NULL DEFAULT 'global',
    scope_department_id INT NOT NULL DEFAULT 0,
    assigned_by INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_role_scope (user_id, role_id, scope_department_id),
    INDEX idx_user_id (user_id),
    INDEX idx_role_id (role_id),
    CONSTRAINT fk_ur_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_ur_role FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    CONSTRAINT fk_ur_assigned_by FOREIGN KEY (assigned_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Token 管理表
CREATE TABLE user_tokens (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    token_type ENUM('refresh', 'reset_password', 'email_verify') NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    expires_at DATETIME NOT NULL,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_token_hash (token_hash),
    CONSTRAINT fk_ut_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 登入紀錄表
CREATE TABLE login_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NULL,
    attempted_email VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45) NULL,
    user_agent VARCHAR(500) NULL,
    device_type VARCHAR(20) NULL,
    login_status ENUM('success', 'failed') NOT NULL,
    failure_reason VARCHAR(100) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at),
    CONSTRAINT fk_lh_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 密碼歷史表
CREATE TABLE password_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    password_hash CHAR(60) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    CONSTRAINT fk_ph_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 知識庫模組
-- ============================================================

-- 知識庫資料夾
CREATE TABLE knowledge_folders (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    parent_id INT NULL,
    department_id INT NULL,
    created_by INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_parent_id (parent_id),
    INDEX idx_department_id (department_id),
    CONSTRAINT fk_kf_parent FOREIGN KEY (parent_id) REFERENCES knowledge_folders(id) ON DELETE RESTRICT,
    CONSTRAINT fk_kf_department FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL,
    CONSTRAINT fk_kf_created_by FOREIGN KEY (created_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 知識庫文件
CREATE TABLE knowledge_documents (
    id INT PRIMARY KEY AUTO_INCREMENT,
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(20) NOT NULL,
    folder_id INT NULL,
    permission_level ENUM('public', 'department') NOT NULL DEFAULT 'public',
    department_id INT NULL,
    current_version_id INT NULL,
    uploaded_by INT NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_folder_id (folder_id),
    INDEX idx_uploaded_by (uploaded_by),
    INDEX idx_department_id (department_id),
    CONSTRAINT fk_kd_folder FOREIGN KEY (folder_id) REFERENCES knowledge_folders(id) ON DELETE SET NULL,
    CONSTRAINT fk_kd_department FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL,
    CONSTRAINT fk_kd_uploaded_by FOREIGN KEY (uploaded_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 知識庫文件版本
CREATE TABLE knowledge_doc_versions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    document_id INT NOT NULL,
    version INT NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_size INT NOT NULL,
    checksum VARCHAR(64) NULL,
    restored_from INT NULL,
    status ENUM('pending', 'approved', 'rejected') NOT NULL DEFAULT 'pending',
    vectorization_status ENUM('none', 'processing', 'completed', 'failed') NOT NULL DEFAULT 'none',
    chunk_count INT NOT NULL DEFAULT 0,
    error_message TEXT NULL,
    reviewed_by INT NULL,
    reviewed_at DATETIME NULL,
    reject_reason VARCHAR(500) NULL,
    uploaded_by INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_document_id (document_id),
    INDEX idx_uploaded_by (uploaded_by),
    CONSTRAINT fk_kdv_document FOREIGN KEY (document_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_kdv_reviewed_by FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_kdv_uploaded_by FOREIGN KEY (uploaded_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 添加 current_version_id 外鍵（解決循環依賴）
ALTER TABLE knowledge_documents
    ADD CONSTRAINT fk_kd_current_version FOREIGN KEY (current_version_id) REFERENCES knowledge_doc_versions(id) ON DELETE SET NULL;

-- 知識庫收藏
CREATE TABLE knowledge_favorites (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    document_id INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_document (user_id, document_id),
    INDEX idx_user_id (user_id),
    INDEX idx_document_id (document_id),
    CONSTRAINT fk_kfav_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_kfav_document FOREIGN KEY (document_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 聊天會話
CREATE TABLE chat_conversations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    user_id INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    CONSTRAINT fk_cc_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 聊天訊息
CREATE TABLE chat_messages (
    id INT PRIMARY KEY AUTO_INCREMENT,
    conversation_id INT NOT NULL,
    role ENUM('user', 'assistant') NOT NULL,
    content TEXT NOT NULL,
    sources JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_conversation_id (conversation_id),
    CONSTRAINT fk_cm_conversation FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 初始資料
-- ============================================================

INSERT INTO roles (code, name, description, is_system) VALUES
('super_admin', '超級管理員', '擁有系統所有權限', TRUE),
('dept_admin', '部門管理員', '管理所屬部門的使用者與文件', TRUE),
('editor', '編輯者', '可上傳、編輯文件', TRUE),
('viewer', '檢視者', '僅可檢視文件', TRUE),
('guest', '訪客', '有限的檢視權限', TRUE);

INSERT INTO permissions (code, name, resource, action, description) VALUES
('document:view', '檢視文件', 'document', 'view', '可以檢視文件內容'),
('document:create', '建立文件', 'document', 'create', '可以上傳新文件'),
('document:edit', '編輯文件', 'document', 'edit', '可以編輯文件內容'),
('document:delete', '刪除文件', 'document', 'delete', '可以刪除文件'),
('document:manage', '管理文件', 'document', 'manage', '可以管理文件權限設定'),
('user:view', '檢視使用者', 'user', 'view', '可以檢視使用者資訊'),
('user:create', '建立使用者', 'user', 'create', '可以建立新使用者'),
('user:edit', '編輯使用者', 'user', 'edit', '可以編輯使用者資訊'),
('user:delete', '刪除使用者', 'user', 'delete', '可以刪除使用者'),
('user:manage', '管理使用者', 'user', 'manage', '可以管理使用者角色與權限'),
('department:view', '檢視部門', 'department', 'view', '可以檢視部門資訊'),
('department:create', '建立部門', 'department', 'create', '可以建立新部門'),
('department:edit', '編輯部門', 'department', 'edit', '可以編輯部門資訊'),
('department:delete', '刪除部門', 'department', 'delete', '可以刪除部門'),
('department:manage', '管理部門', 'department', 'manage', '可以管理部門設定'),
('ai:chat', 'AI 對話', 'ai', 'view', '可以使用 AI 問答功能'),
('ai:admin_tools', 'AI 助理管理工具', 'ai', 'admin_tools', '可使用 AI 助理的管理員專屬工具'),
('ai:manage', '管理 AI', 'ai', 'manage', '可以管理 AI 設定'),
('role:view', '檢視角色', 'role', 'view', '可以檢視角色列表'),
('role:create', '建立角色', 'role', 'create', '可以建立新角色'),
('role:edit', '編輯角色', 'role', 'edit', '可以編輯角色權限'),
('role:delete', '刪除角色', 'role', 'delete', '可以刪除角色'),
('system:view', '檢視系統', 'system', 'view', '可以檢視系統資訊'),
('system:manage', '管理系統', 'system', 'manage', '可以管理系統設定');

-- 超級管理員：所有權限
INSERT INTO role_permissions (role_id, permission_id)
SELECT (SELECT id FROM roles WHERE code = 'super_admin'), id FROM permissions;

-- 部門管理員
INSERT INTO role_permissions (role_id, permission_id)
SELECT (SELECT id FROM roles WHERE code = 'dept_admin'), id FROM permissions
WHERE code IN ('document:view', 'document:create', 'document:edit', 'document:delete',
               'user:view', 'user:create', 'user:edit', 'department:view', 'department:edit', 'ai:chat');

-- 編輯者
INSERT INTO role_permissions (role_id, permission_id)
SELECT (SELECT id FROM roles WHERE code = 'editor'), id FROM permissions
WHERE code IN ('document:view', 'document:create', 'document:edit', 'ai:chat');

-- 檢視者
INSERT INTO role_permissions (role_id, permission_id)
SELECT (SELECT id FROM roles WHERE code = 'viewer'), id FROM permissions
WHERE code IN ('document:view', 'ai:chat');

-- 訪客
INSERT INTO role_permissions (role_id, permission_id)
SELECT (SELECT id FROM roles WHERE code = 'guest'), id FROM permissions
WHERE code = 'document:view';

SELECT '資料庫 AI_G2_DB (EMKS) 建置完成！' AS message;
