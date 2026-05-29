FROM eclipse-temurin:21

ENV H2_VERSION=2.2.224
WORKDIR /opt/h2

RUN curl -fsSL https://repo1.maven.org/maven2/com/h2database/h2/${H2_VERSION}/h2-${H2_VERSION}.jar -o h2.jar

EXPOSE 8082 9092

CMD ["java", "-cp", "h2.jar", "org.h2.tools.Server", \
     "-tcp", "-tcpAllowOthers", \
     "-web", "-webAllowOthers", \
     "-ifNotExists"]