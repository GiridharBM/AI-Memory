---
title: "Docker Commands Cheat Sheet"
source: "D:\\Projects\\Personal AI Memory\\data\\inbox\\Docker CheatSheet ApnaCollege.pdf"
source_type: "pdf"
filename: "Docker CheatSheet ApnaCollege.pdf"
generated_date: "2026-08-25T07:51:43.735920+00:00"
reading_time_minutes: 1
difficulty: "beginner"
categories:
  - "Technology"
  - "Devops"
  - "Docker"
  - "Cheat Sheet"
  - "Command Reference"
keywords:
  - "docker"
  - "commands"
  - "containers"
  - "images"
  - "volumes"
  - "networks"
  - "dockerhub"
  - "prune"
  - "build"
  - "run"
tags:
  - "docker"
  - "commands"
  - "containers"
  - "images"
  - "volumes"
  - "networks"
  - "dockerhub"
  - "prune"
processing_confidence: 0.90
---
<!-- PAM:BEGIN MANAGED -->
# Docker Cheat Sheet Commands

## Summary

This document provides Docker commands for managing images, containers, volumes, networks, and DockerHub interactions. It includes commands for building, running, and deleting containers, as well as volume and network management.

The Docker Cheat Sheet covers essential commands for working with Docker, including listing and deleting images, building images from Dockerfiles, running containers in the foreground or background, and setting environment variables. It also explains how to manage volumes, both named and anonymous, and how to handle networks. The guide includes troubleshooting commands like fetching container logs and opening shells inside running containers. Additionally, it provides instructions for interacting with DockerHub, such as pulling and pushing images, and searching for images. The cheat sheet is organized into sections for images, containers, volumes, networks, and DockerHub operations.

## Table of Contents

- [[#Reading Time|Reading Time]]
- [[#Difficulty Level|Difficulty Level]]
- [[#Keywords|Keywords]]
- [[#Categories|Categories]]
- [[#Key Concepts|Key Concepts]]
- [[#Definitions|Definitions]]
- [[#Important Entities|Important Entities]]
- [[#Related Topics|Related Topics]]
- [[#Suggested Related Notes|Suggested Related Notes]]
- [[#Suggested Backlinks|Suggested Backlinks]]
- [[#Frequently Asked Questions|Frequently Asked Questions]]
- [[#Flashcards|Flashcards]]
- [[#Multiple Choice Questions|Multiple Choice Questions]]
- [[#Short Answer Questions|Short Answer Questions]]
- [[#Long Answer Questions|Long Answer Questions]]
- [[#Revision Notes|Revision Notes]]
- [[#Tags|Tags]]
- [[#Metadata|Metadata]]
- [[#References|References]]

## Reading Time

**5 minutes**

## Difficulty Level

**Beginner**

## Keywords

`docker commands`, `docker images`, `docker containers`, `docker volumes`, `docker networks`, `docker hub`, `docker run`, `docker build`, `docker pull`, `docker push`, `docker volume`, `docker network`, `docker inspect`, `docker logs`, `docker exec`

## Categories

- Docker
- Commands
- Cheat Sheet
- Devops
- System Administration

## Key Concepts

- [[Docker Images]] (high): Images are the building blocks of Docker containers. They are created from Dockerfiles and can be pulled from or pushed to DockerHub.
- [[Docker Containers]] (high): Containers are runtime instances of Docker images. They can be started, stopped, and deleted, with options to run in the foreground or background.
- [[Docker Volumes]] (medium): Volumes are used for persistent data storage in Docker. They can be named or anonymous and support bind mounts for host file system integration.
- [[Docker Networks]] (medium): Networks allow containers to communicate with each other and the outside world. Docker provides commands to create, remove, and manage networks.
- [[DockerHub]] (high): DockerHub is a registry where Docker images are stored and shared. Users can pull images from or push their own images to DockerHub.

## Definitions

- [[docker images]]: A list of all local Docker images available on the system.
- [[docker containers]]: A list of all local Docker containers, including both running and stopped ones.
- [[docker volumes]]: A list of all Docker volumes, which are used for data persistence.
- [[docker networks]]: A list of all Docker networks, which enable communication between containers.
- [[docker run]]: A command to create and run a new Docker container.
- [[docker build]]: A command to build a Docker image from a Dockerfile.
- [[docker pull]]: A command to download a Docker image from DockerHub.
- [[docker push]]: A command to upload a Docker image to DockerHub.
- [[docker exec]]: A command to execute a command inside a running Docker container.
- [[docker inspect]]: A command to get detailed information about a Docker container or image.

## Important Entities

- [[Docker]] (technology): An open-source platform for developing, shipping, and running applications in containers.
- [[DockerHub]] (organization): A cloud-based registry service for Docker images.
- [[docker images]] (concept): A command to list all local Docker images.
- [[docker containers]] (concept): A command to list all local Docker containers.
- [[docker volumes]] (concept): A command to list all Docker volumes.
- [[docker networks]] (concept): A command to list all Docker networks.
- [[docker run]] (concept): A command to create and run a Docker container.
- [[docker build]] (concept): A command to build a Docker image from a Dockerfile.
- [[docker pull]] (concept): A command to pull a Docker image from DockerHub.
- [[docker push]] (concept): A command to push a Docker image to DockerHub.

## Related Topics

- [[Containerization]]: Docker is a key tool in containerization, allowing applications to be packaged and run consistently across environments.
- [[DevOps]]: Docker is widely used in DevOps practices for automation, deployment, and infrastructure as code.
- [[Cloud Computing]]: Docker supports cloud computing by enabling containerized applications to run on various cloud platforms.
- [[System Administration]]: Docker provides tools for managing system resources and services through containers.
- [[Software Development]]: Docker is integral to modern software development for testing, deployment, and CI/CD pipelines.
- [[Networking]]: Docker networks allow containers to communicate and interact with external networks.
- [[Data Persistence]]: Docker volumes provide solutions for data persistence in containerized applications.
- [[Version Control]]: Docker images are versioned, allowing for precise control over application versions.
- [[CI/CD]]: Docker is used in CI/CD pipelines for building, testing, and deploying applications.
- [[Container Orchestration]]: While Docker itself doesn't orchestrate containers, it's often used with tools like Kubernetes for managing containerized applications.

## Suggested Related Notes

- [[Dockerfile Best Practices]]
- [[Docker Networking Configuration]]
- [[Docker Volume Management]]
- [[Docker Hub Authentication]]
- [[Docker Container Troubleshooting]]

## Suggested Backlinks

- [[Dockerfile Concepts]]
- [[Docker Networking]]
- [[Docker Volumes]]
- [[Docker Hub Usage]]
- [[Docker Container Management]]

## Frequently Asked Questions

**Q1: What command is used to list all local Docker images?**
A1: docker images

**Q2: How do you run a Docker container in the background?**
A2: docker run -d <image_name>

**Q3: What command is used to delete a Docker container?**
A3: docker rm <container_name> or <container_id>

**Q4: How do you create a named Docker volume?**
A4: docker volume create <volume_name>

**Q5: What command is used to fetch logs from a running container?**
A5: docker logs <container_name> or <container_id>

**Q6: How do you inspect a Docker container?**
A6: docker inspect <container_name> or <container_id>

**Q7: What command is used to push a Docker image to DockerHub?**
A7: docker push <username>/<image_name>

**Q8: How do you set environment variables in a Docker container?**
A8: docker run -e <var_name>=<var_value> <image_name>

**Q9: What command is used to create a Docker network?**
A9: docker network create <network_name>

**Q10: How do you remove all unused Docker networks?**
A10: docker network prune

## Flashcards

**Card 1 - Front:** What is the command to list all local Docker images?
**Back:** docker images

**Card 2 - Front:** How do you run a Docker container in the background?
**Back:** docker run -d <image_name>

**Card 3 - Front:** What command is used to delete a Docker container?
**Back:** docker rm <container_name> or <container_id>

**Card 4 - Front:** How do you create a named Docker volume?
**Back:** docker volume create <volume_name>

**Card 5 - Front:** What command is used to fetch logs from a running container?
**Back:** docker logs <container_name> or <container_id>

**Card 6 - Front:** How do you inspect a Docker container?
**Back:** docker inspect <container_name> or <container_id>

**Card 7 - Front:** What command is used to push a Docker image to DockerHub?
**Back:** docker push <username>/<image_name>

**Card 8 - Front:** How do you set environment variables in a Docker container?
**Back:** docker run -e <var_name>=<var_value> <image_name>

**Card 9 - Front:** What command is used to create a Docker network?
**Back:** docker network create <network_name>

**Card 10 - Front:** How do you remove all unused Docker networks?
**Back:** docker network prune

## Multiple Choice Questions

**1. Which command is used to list all local Docker images?**
   A. [ ] docker ps
   B. [X] docker images
   C. [ ] docker containers
   D. [ ] docker list
   *Explanation: The 'docker images' command lists all local Docker images on the system.*

**2. How do you run a Docker container in the background?**
   A. [X] docker run -d <image_name>
   B. [ ] docker run -b <image_name>
   C. [ ] docker run -f <image_name>
   D. [ ] docker run -s <image_name>
   *Explanation: The '-d' flag in 'docker run' starts the container in the background.*

**3. What command is used to delete a Docker container?**
   A. [X] docker rm <container_name>
   B. [ ] docker del <container_name>
   C. [ ] docker remove <container_name>
   D. [ ] docker delete <container_name>
   *Explanation: The 'docker rm' command is used to delete a Docker container.*

**4. How do you create a named Docker volume?**
   A. [ ] docker volume create <volume_name>
   B. [ ] docker volume make <volume_name>
   C. [ ] docker volume new <volume_name>
   D. [ ] docker volume define <volume_name>
   *Explanation: The 'docker volume create' command creates a named Docker volume.*

**5. What command is used to fetch logs from a running container?**
   A. [X] docker logs <container_name>
   B. [ ] docker log <container_name>
   C. [ ] docker getlogs <container_name>
   D. [ ] docker showlogs <container_name>
   *Explanation: The 'docker logs' command retrieves logs from a running Docker container.*

**6. How do you inspect a Docker container?**
   A. [X] docker inspect <container_name>
   B. [ ] docker info <container_name>
   C. [ ] docker details <container_name>
   D. [ ] docker describe <container_name>
   *Explanation: The 'docker inspect' command provides detailed information about a Docker container.*

**7. What command is used to push a Docker image to DockerHub?**
   A. [X] docker push <username>/<image_name>
   B. [ ] docker upload <username>/<image_name>
   C. [ ] docker send <username>/<image_name>
   D. [ ] docker transfer <username>/<image_name>
   *Explanation: The 'docker push' command uploads a Docker image to DockerHub.*

**8. How do you set environment variables in a Docker container?**
   A. [X] docker run -e <var_name>=<var_value> <image_name>
   B. [ ] docker run -set <var_name>=<var_value> <image_name>
   C. [ ] docker run -env <var_name>=<var_value> <image_name>
   D. [ ] docker run -var <var_name>=<var_value> <image_name>
   *Explanation: The '-e' flag in 'docker run' sets environment variables for the container.*

**9. What command is used to create a Docker network?**
   A. [X] docker network create <network_name>
   B. [ ] docker net create <network_name>
   C. [ ] docker network make <network_name>
   D. [ ] docker net make <network_name>
   *Explanation: The 'docker network create' command is used to create a new Docker network.*

**10. How do you remove all unused Docker networks?**
   A. [X] docker network prune
   B. [ ] docker network remove all
   C. [ ] docker network clear
   D. [ ] docker network delete all
   *Explanation: The 'docker network prune' command removes all unused Docker networks.*

## Short Answer Questions

**1. What is the purpose of the 'docker images' command?**
*Answer: To list all local Docker images available on the system.*

**2. How can you run a Docker container in the background?**
*Answer: Using the '-d' flag with the 'docker run' command.*

**3. What command is used to delete a Docker container?**
*Answer: docker rm <container_name> or <container_id>*

**4. How do you create a named Docker volume?**
*Answer: Using the 'docker volume create <volume_name>' command.*

**5. What command is used to fetch logs from a running container?**
*Answer: docker logs <container_name> or <container_id>*

**6. How do you inspect a Docker container?**
*Answer: Using the 'docker inspect' command with the container name or ID.*

**7. What command is used to push a Docker image to DockerHub?**
*Answer: docker push <username>/<image_name>*

**8. How do you set environment variables in a Docker container?**
*Answer: Using the '-e' flag with the 'docker run' command.*

**9. What command is used to create a Docker network?**
*Answer: docker network create <network_name>*

**10. How do you remove all unused Docker networks?**
*Answer: Using the 'docker network prune' command.*

## Long Answer Questions

**1. Explain the purpose and usage of Docker volumes.**

Docker volumes are used for persistent data storage in containers. They can be named or anonymous. Named volumes are created with 'docker volume create <volume_name>' and can be mounted to containers using the '-v' or '--mount' option. Anonymous volumes are created automatically when a container is run with the '-v' flag without specifying a name. Volumes allow data to persist even if the container is deleted, making them useful for databases, caches, and other applications requiring data retention.

**2. Describe the process of building a Docker image from a Dockerfile.**

To build a Docker image from a Dockerfile, use the 'docker build' command followed by the path to the Dockerfile and the desired image name and tag. For example, 'docker build -t <image_name>:<version> .' builds the image using the Dockerfile in the current directory. The '-t' flag tags the image with a name and version. The '.' at the end specifies the build context, which includes all files in the directory. Building without caching can be done with the '--no-cache' option to ensure a clean build.

**3. What are the key differences between Docker containers and Docker images?**

Docker images are static, read-only templates used to create containers. They are built from Dockerfiles and contain the application and its dependencies. Containers are runtime instances of images, which are started, stopped, and managed. Containers can have their own configurations, such as environment variables and network settings, and can be modified while running. Images are used for deployment and distribution, while containers are the executing entities.

**4. How does Docker Hub function in the Docker ecosystem?**

Docker Hub is a cloud-based registry where Docker images are stored and shared. Users can pull images from Docker Hub using the 'docker pull' command, which downloads the image to their local machine. Images can also be pushed to Docker Hub using 'docker push', making them available for others to use. Docker Hub supports both public and private repositories, allowing for collaboration and version control of Docker images. It also provides documentation, automation, and integration with CI/CD pipelines.

**5. Explain the role of Docker networks in container communication.**

Docker networks enable communication between containers and with external services. When containers are connected to the same network, they can communicate with each other using their container names as hostnames. Docker provides commands to create, manage, and inspect networks, allowing for custom network configurations. Networks can be used to isolate services, set up load balancing, and manage traffic between containers. This is essential for applications that require multiple containers to work together, such as microservices architectures.

## Revision Notes

### Key Concepts

- Docker images are the foundation of containers, built from Dockerfiles.
- Docker containers are runtime instances of images, which can be started, stopped, and deleted.
- Volumes provide persistent storage for data in containers, supporting named and anonymous types.
- Docker networks enable communication between containers and external services.
- Docker Hub is a registry for storing and sharing Docker images.

## Tags

- #docker-commands
- #docker-images
- #docker-containers
- #docker-volumes
- #docker-networks
- #docker-hub
- #docker-run
- #docker-build

## Metadata

- **Word Count:** 213
- **Page Count:** 1
- **Language:** en
- **Source URL:** file:///D:/Projects/Personal AI Memory/data/inbox/Docker CheatSheet ApnaCollege.pdf

## References

- Source: D:\Projects\Personal AI Memory\data\inbox\Docker CheatSheet ApnaCollege.pdf
- Source type: pdf
- Original filename: Docker CheatSheet ApnaCollege.pdf
- Generated date: 2026-08-26T04:43:15.016610+00:00
- Source title: Docker CheatSheet ApnaCollege
- Processing Confidence: 90%

## Wiki Navigation

- [[index]]
- [[overview]]
- [[log]]
<!-- PAM:END MANAGED -->
