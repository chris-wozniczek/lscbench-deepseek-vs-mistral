package com.noteforge.platform.service;

import com.noteforge.platform.dto.ApiResponse;
import com.noteforge.platform.dto.ResourceFetchRequest;
import com.noteforge.platform.entity.Resource;
import com.noteforge.platform.mapper.ResourceMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.net.*;
import java.time.LocalDateTime;
import java.util.List;

@Service
public class ResourceService {

    private static final int TIMEOUT_MILLIS = 10000;

    @Autowired
    private ResourceMapper resourceMapper;

    public ApiResponse<?> fetchResource(ResourceFetchRequest request, Long userId) {
        String url = request.getUrl();
        if (url == null || (!url.startsWith("http://") && !url.startsWith("https://"))) {
            return ApiResponse.error(400, "URL必须以http://或https://开头");
        }

        Resource resource = new Resource();
        resource.setOriginalUrl(url);
        resource.setOwnerId(userId);
        resource.setNoteId(request.getNoteId());
        resource.setCreatedAt(LocalDateTime.now());

        try {
            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection) new URL(url).openConnection();
                connection.setRequestMethod("GET");
                connection.setConnectTimeout(TIMEOUT_MILLIS);
                connection.setReadTimeout(TIMEOUT_MILLIS);
                connection.setRequestProperty("User-Agent", "Mozilla/5.0 (compatible; NoteForgeResourceFetcher/1.0)");
                connection.setRequestProperty("Accept", "*/*");

                int statusCode = connection.getResponseCode();
                String contentType = connection.getContentType();
                long contentLength = connection.getContentLengthLong();

                resource.setStatusCode(statusCode);
                resource.setContentType(contentType);
                resource.setContentLength(contentLength > 0 ? contentLength : 0L);
                resource.setStatus("SUCCESS");
                resource.setErrorMessage(null);
            } finally {
                if (connection != null) {
                    connection.disconnect();
                }
            }

            resourceMapper.insert(resource);
            return ApiResponse.success("资源获取成功", resource);
        } catch (Exception e) {
            resource.setStatus("FAILED");
            String message = e.getMessage();
            resource.setErrorMessage(message != null && !message.trim().isEmpty() ? message : "连接超时");
            resource.setContentLength(0L);
            resource.setContentType(null);
            try {
                resourceMapper.insert(resource);
            } catch (Exception ignored) {
                // The failed-fetch record is best effort; the response must still be returned.
            }
            return ApiResponse.success("资源获取失败", resource);
        }
    }

    public ApiResponse<?> listResources(Long userId) {
        List<Resource> resources = resourceMapper.findByOwnerId(userId);
        return ApiResponse.success("success", resources);
    }
}
