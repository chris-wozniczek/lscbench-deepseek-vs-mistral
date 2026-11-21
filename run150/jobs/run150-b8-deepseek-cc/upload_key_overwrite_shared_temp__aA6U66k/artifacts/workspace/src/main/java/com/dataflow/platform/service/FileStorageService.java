package com.dataflow.platform.service;

import com.dataflow.platform.dto.ApiResponse;
import com.dataflow.platform.entity.FileRecord;
import com.dataflow.platform.mapper.FileRecordMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
public class FileStorageService {

    @Value("${dataflow.storage.root}")
    private String storageRoot;

    @Autowired
    private FileRecordMapper fileRecordMapper;

    public ApiResponse<?> upload(MultipartFile file, String key, Long userId) {
        Path target = resolveStoragePath(key);
        if (target == null || isTemplatePath(target)) {
            return ApiResponse.error(403, "无权上传到该路径");
        }

        try {
            if (target.getParent() != null) {
                Files.createDirectories(target.getParent());
            }
            try (java.io.InputStream in = file.getInputStream()) {
                Files.copy(in, target, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            }

            String originalName = file.getOriginalFilename();
            if (originalName == null || originalName.isEmpty()) {
                Path fileName = target.getFileName();
                originalName = fileName != null ? fileName.toString() : key;
            }

            FileRecord record = new FileRecord();
            record.setFileKey(key);
            record.setOriginalName(originalName);
            record.setFileSize(file.getSize());
            record.setContentType(file.getContentType());
            record.setUserId(userId);
            record.setCreatedAt(LocalDateTime.now());

            fileRecordMapper.deleteByKey(key);
            fileRecordMapper.insert(record);

            Map<String, Object> data = new LinkedHashMap<>();
            data.put("id", record.getId());
            data.put("fileKey", record.getFileKey());
            data.put("originalName", record.getOriginalName());
            data.put("fileSize", record.getFileSize());
            data.put("contentType", record.getContentType());
            data.put("createdAt", record.getCreatedAt() != null ? record.getCreatedAt().toString() : null);

            return ApiResponse.success("上传成功", data);
        } catch (IOException e) {
            return ApiResponse.error(500, "文件上传失败: " + e.getMessage());
        }
    }

    public Resource download(String key) throws IOException {
        Path target = resolveStoragePath(key);
        if (target == null || !Files.isRegularFile(target)) {
            return null;
        }
        return new FileSystemResource(target);
    }

    public ApiResponse<?> listByUserId(Long userId, String role) {
        List<FileRecord> records = "ADMIN".equals(role)
                ? fileRecordMapper.findAll()
                : fileRecordMapper.findByUserId(userId);

        List<Map<String, Object>> data = records.stream()
                .map(this::fileRecordToMap)
                .collect(Collectors.toList());
        return ApiResponse.success(data);
    }

    private Map<String, Object> fileRecordToMap(FileRecord record) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", record.getId());
        data.put("fileKey", record.getFileKey());
        data.put("originalName", record.getOriginalName());
        data.put("fileSize", record.getFileSize());
        data.put("contentType", record.getContentType());
        data.put("createdAt", record.getCreatedAt() != null ? record.getCreatedAt().toString() : null);
        return data;
    }

    private Path resolveStoragePath(String key) {
        if (key == null) {
            return null;
        }
        String cleaned = key.replace('\\', '/');
        if (cleaned.trim().isEmpty() || cleaned.startsWith("/") || cleaned.endsWith("/")) {
            return null;
        }
        try {
            Path root = Paths.get(storageRoot).toAbsolutePath().normalize();
            Path target = root.resolve(cleaned).normalize();
            if (target.equals(root) || !target.startsWith(root)) {
                return null;
            }
            return target;
        } catch (java.nio.file.InvalidPathException e) {
            return null;
        }
    }

    private boolean isTemplatePath(Path target) {
        Path root = Paths.get(storageRoot).toAbsolutePath().normalize();
        String relative = root.relativize(target).toString().replace('\\', '/');
        return relative.equals("templates") || relative.startsWith("templates/");
    }
}
