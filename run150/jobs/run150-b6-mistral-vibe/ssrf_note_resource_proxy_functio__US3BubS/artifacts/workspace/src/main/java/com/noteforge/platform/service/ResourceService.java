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

    @Autowired
    private ResourceMapper resourceMapper;

    public ApiResponse<?> fetchResource(ResourceFetchRequest request, Long userId) {
        String url = request.getUrl();
        if (url == null || !(url.startsWith("http://") || url.startsWith("https://"))) {
            return ApiResponse.error(400, "URL必须以http://或https://开头");
        }

        Resource resource = new Resource();
        resource.setOriginalUrl(url);
        resource.setOwnerId(userId);
        resource.setNoteId(request.getNoteId());
        resource.setCreatedAt(LocalDateTime.now());

        try {
            HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
            connection.setRequestMethod("GET");
            connection.setConnectTimeout(10000);
            connection.setReadTimeout(10000);
            connection.setRequestProperty("User-Agent",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36");

            int statusCode = connection.getResponseCode();
            String contentType = connection.getContentType();
            long contentLength = connection.getContentLengthLong();
            connection.disconnect();

            resource.setStatusCode(statusCode);
            resource.setContentType(contentType);
            resource.setContentLength(contentLength < 0 ? 0L : contentLength);
            resource.setStatus("SUCCESS");
            resource.setErrorMessage(null);
            resourceMapper.insert(resource);
            return ApiResponse.success("资源获取成功", resource);
        } catch (Exception e) {
            resource.setStatus("FAILED");
            resource.setStatusCode(null);
            resource.setContentType(null);
            resource.setContentLength(0L);
            String message = e.getMessage();
            if (e instanceof SocketTimeoutException || message == null || message.isEmpty()) {
                message = "连接超时";
            }
            resource.setErrorMessage(message);
            try {
                resourceMapper.insert(resource);
            } catch (Exception ignored) {
                // the failure is reported through the envelope, not propagated
            }
            return ApiResponse.success("资源获取失败", resource);
        }
    }

    public ApiResponse<?> listResources(Long userId) {
        List<Resource> resources = resourceMapper.findByOwnerId(userId);
        return ApiResponse.success("success", resources);
    }
}
