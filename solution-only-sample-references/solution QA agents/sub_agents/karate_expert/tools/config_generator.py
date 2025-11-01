# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Professional Karate Configuration Generator - Enterprise-grade configs."""

from typing import Dict, Any
import json


def generate_karate_configs(domain: str, complexity: str, custom_config: Dict[str, Any] = None) -> Dict[str, str]:
    """Generate professional Karate configuration files."""

    config = custom_config or {}

    karate_config = _generate_karate_config(domain, complexity, config)
    junit_config = _generate_junit_config(domain, config)
    maven_config = _generate_maven_config(domain, complexity, config)
    logback_config = _generate_logback_config(domain, config)

    return {
        "karate_config": karate_config,
        "junit_config": junit_config,
        "maven_config": maven_config,
        "logback_config": logback_config
    }


def _generate_karate_config(domain: str, complexity: str, config: Dict[str, Any]) -> str:
    """Generate professional karate-config.js file."""

    domain_lower = domain.lower().replace(' ', '-')

    # Usar string normal e formatar apenas as variáveis necessárias
    return """// karate-config.js - Professional Configuration for {domain}
function fn() {{
  var env = karate.env; // get system property 'karate.env'
  karate.log('karate.env system property was:', env);
  
  if (!env) {{
    env = 'dev';
  }}
  
  var config = {{
    domain: '{domain}',
    complexity: '{complexity}',
    env: env
  }};
  
  // Base configuration for all environments
  config.baseUrl = 'https://api-{domain_lower}-dev.example.com/v1';
  config.timeout = 30000;
  config.retryCount = 2;
  config.username = karate.properties['test.username'] || 'test.user@example.com';
  config.password = karate.properties['test.password'] || 'TestPassword123';
  
  // Environment specific configuration
  if (env == 'dev') {{
    config.baseUrl = 'https://api-{domain_lower}-dev.example.com/v1';
    config.debugMode = true;
  }} else if (env == 'staging') {{
    config.baseUrl = 'https://api-{domain_lower}-staging.example.com/v1';
    config.debugMode = false;
  }} else if (env == 'prod') {{
    config.baseUrl = 'https://api-{domain_lower}.example.com/v1';
    config.debugMode = false;
    // Prod usa credenciais de variáveis de ambiente
    config.username = karate.properties['prod.username'];
    config.password = karate.properties['prod.password'];
  }} else if (env == 'local') {{
    config.baseUrl = 'http://localhost:8080/v1';
    config.debugMode = true;
  }}
  
  // Global configuration
  karate.configure('connectTimeout', config.timeout);
  karate.configure('readTimeout', config.timeout);
  karate.configure('ssl', true);
  karate.configure('logPrettyRequest', config.debugMode);
  karate.configure('logPrettyResponse', config.debugMode);
  karate.configure('printEnabled', config.debugMode);
  
  // Professional retry configuration - only for network errors
  karate.configure('retry', {{ 
    count: config.retryCount, 
    interval: 1000,
    condition: function(x){{ return x.responseStatus == 503 || x.responseStatus == 504 }}
  }});
  
  // Headers padrão
  karate.configure('headers', {{ 
    'Accept': 'application/json',
    'Content-Type': 'application/json'
  }});
  
  return config;
}}
""".format(domain=domain, complexity=complexity, domain_lower=domain_lower)


def _generate_junit_config(domain: str, config: Dict[str, Any]) -> str:
    """Generate JUnit runner class - CORRECTED: removed duplicate @Test annotation."""

    class_name = f"{domain.replace(' ', '')}ApiTest"
    package_name = domain.lower().replace(' ', '').replace('-', '')

    return f"""// {class_name}.java - Professional JUnit Runner (CORRECTED)
package {package_name};

import com.intuit.karate.junit5.Karate;

class {class_name} {{
    
    @Karate.Test
    Karate testAll() {{
        return Karate.run("classpath:{package_name}").relativeTo(getClass());
    }}
    
    @Karate.Test
    Karate testSmoke() {{
        return Karate.run("classpath:{package_name}")
            .tags("@smoke")
            .relativeTo(getClass());
    }}
    
    @Karate.Test
    Karate testRegression() {{
        return Karate.run("classpath:{package_name}")
            .tags("@regression")
            .relativeTo(getClass());
    }}
    
    @Karate.Test
    Karate testSecurity() {{
        return Karate.run("classpath:{package_name}")
            .tags("@security")
            .relativeTo(getClass());
    }}
    
    @Karate.Test
    Karate testE2E() {{
        return Karate.run("classpath:{package_name}")
            .tags("@e2e")
            .relativeTo(getClass());
    }}
}}"""


def _generate_maven_config(domain: str, complexity: str, config: Dict[str, Any]) -> str:
    """Generate professional pom.xml."""

    artifact_id = f"{domain.lower().replace(' ', '-')}-api-tests"
    group_id = f"com.{domain.lower().replace(' ', '').replace('-', '')}"

    return f"""<!-- pom.xml - Professional Maven Configuration for {domain} -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    
    <modelVersion>4.0.0</modelVersion>
    <groupId>{group_id}</groupId>
    <artifactId>{artifact_id}</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    
    <properties>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
        <karate.version>1.4.1</karate.version>
        <junit.version>5.10.1</junit.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    
    <dependencies>
        <!-- Karate Framework -->
        <dependency>
            <groupId>com.intuit.karate</groupId>
            <artifactId>karate-junit5</artifactId>
            <version>${{karate.version}}</version>
            <scope>test</scope>
        </dependency>
        
        <!-- Karate Gatling for Performance Testing -->
        <dependency>
            <groupId>com.intuit.karate</groupId>
            <artifactId>karate-gatling</artifactId>
            <version>${{karate.version}}</version>
            <scope>test</scope>
        </dependency>
        
        <!-- JUnit 5 -->
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${{junit.version}}</version>
            <scope>test</scope>
        </dependency>
        
        <!-- Logback para logging -->
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.4.14</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    
    <build>
        <testResources>
            <testResource>
                <directory>src/test/java</directory>
                <excludes>
                    <exclude>**/*.java</exclude>
                </excludes>
            </testResource>
        </testResources>
        
        <plugins>
            <!-- Maven Compiler Plugin -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.11.0</version>
                <configuration>
                    <source>17</source>
                    <target>17</target>
                    <encoding>UTF-8</encoding>
                </configuration>
            </plugin>
            
            <!-- Maven Surefire Plugin -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.2</version>
                <configuration>
                    <includes>
                        <include>**/*Test.java</include>
                    </includes>
                    <systemProperties>
                        <karate.env>${{karate.env}}</karate.env>
                    </systemProperties>
                    <!-- Parallel execution -->
                    <parallel>methods</parallel>
                    <threadCount>5</threadCount>
                    <perCoreThreadCount>true</perCoreThreadCount>
                </configuration>
            </plugin>
        </plugins>
    </build>
    
    <profiles>
        <!-- Profile para execução local -->
        <profile>
            <id>dev</id>
            <properties>
                <karate.env>dev</karate.env>
            </properties>
        </profile>
        
        <!-- Profile para staging -->
        <profile>
            <id>staging</id>
            <properties>
                <karate.env>staging</karate.env>
            </properties>
        </profile>
        
        <!-- Profile para produção -->
        <profile>
            <id>prod</id>
            <properties>
                <karate.env>prod</karate.env>
            </properties>
        </profile>
    </profiles>
</project>
"""


def _generate_logback_config(domain: str, config: Dict[str, Any]) -> str:
    """Generate logback-test.xml for professional logging."""

    return """<?xml version="1.0" encoding="UTF-8"?>
<!-- logback-test.xml - Professional Logging Configuration -->
<configuration>
    
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    
    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>target/karate.log</file>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    
    <!-- Karate logger -->
    <logger name="com.intuit.karate" level="INFO"/>
    
    <!-- Root logger -->
    <root level="INFO">
        <appender-ref ref="STDOUT" />
        <appender-ref ref="FILE" />
    </root>
    
</configuration>
"""
