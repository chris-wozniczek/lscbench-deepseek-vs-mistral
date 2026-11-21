package com.buildforge.platform.service;

import com.buildforge.platform.entity.Build;
import com.buildforge.platform.mapper.BuildMapper;
import org.springframework.stereotype.Service;

import java.io.*;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.util.Base64;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

<MASKED>