# Deploying PitWall: Docker on one EC2 instance

**Status: not deployed yet.** (Decision: Docker on EC2, on AWS free-plan credits.) The container is built and tested locally (see "What was and wasn't tested").
**No AWS command below has been run.** You run each one, so you see what it does; if one fails, paste the output.

## The free window, and what happens when it closes

This runs on AWS free-plan credits. On 2026-11-18 the balance was $78, expiring in 99 days (about **2027-02-25**; set a reminder
for 2027-02-11). A free plan ends after 6 months or when the credits run out, whichever
comes first, and then the account closes unless you upgrade to a paid plan
([AWS announcement](https://aws.amazon.com/about-aws/whats-new/2025/07/aws-free-tier-credits-month-free-plan)). ECS has no charge
of its own, but a server does: roughly $17 a month for this setup with a `t4g.small` (a rough figure from memory; confirm in the Pricing Calculator).

- **Now:** read your credit balance and expiry under Billing -> Credits, and note the date.
- **A month before it ends:** either upgrade, or move the demo. Streamlit Community Cloud is free and `app.py` already works
  there (it adds `src/` to the import path); create the app at <https://share.streamlit.io> from this repo, main file `app.py`,
  Python 3.13, then point the README at the new URL.
- Don't put an AWS URL on your resume without that date in mind.

## What you will create

| Resource | Why | Cost note |
|---|---|---|
| 1 EC2 instance, `t4g.small` (ARM, 2 GB RAM) | runs the container; the app peaks near 470 MB per session, so 1 GB is too tight | on-demand hourly price |
| 16 GB gp3 EBS volume | Docker image (1.3 GB) + OS | per GB-month |
| 1 Elastic IP | a stable address | public IPv4 addresses are billed hourly |
| Security group | SSH from your IP only, HTTP from anywhere | free |
| Budget alert | tells you before the bill surprises you | free |

Prices change: check the AWS Pricing Calculator for your region before launching, and set the budget alert first.
Everything is torn down by the commands in section 9. **Tear it down when you stop using it.**

## 0. Before launching anything

1. **Don't use the root account's keys.** Use an IAM user or Identity Center user with MFA, and make it your CLI profile
   (`aws configure`, or `aws configure sso`). Check who you are: `aws sts get-caller-identity`.
2. **Budget alert.** Edit `deploy/budget-notifications.json` (replace `YOU@example.com` twice) and, if you like,
   the amount in `deploy/budget.json` (30 USD per month by default: a signal that something is wrong, not a target), then:

   ```bash
   ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
   aws budgets create-budget --account-id $ACCOUNT \
       --budget file://deploy/budget.json \
       --notifications-with-subscribers file://deploy/budget-notifications.json
   ```
   AWS emails you to confirm the subscription. It alerts at 80% of actual spend and 100% of forecast spend.

## 1. Settings

```bash
export AWS_DEFAULT_REGION=us-east-1          # use the region closest to you
MYIP=$(curl -s https://checkip.amazonaws.com)
AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64 \
      --query Parameter.Value --output text)
echo "$MYIP  $AMI"
```

## 2. SSH key pair

```bash
aws ec2 create-key-pair --key-name pitwall --key-type ed25519 --query KeyMaterial --output text > ~/.ssh/pitwall.pem
chmod 400 ~/.ssh/pitwall.pem
```

## 3. Security group (SSH only from your IP, web from anywhere)

```bash
VPC=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)
SG=$(aws ec2 create-security-group --group-name pitwall --description "PitWall app" --vpc-id $VPC \
     --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 22 --cidr $MYIP/32
aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 80 --cidr 0.0.0.0/0
```
If `$VPC` comes back as `None`, the account has no default VPC: stop and ask.

## 4. Launch the instance

`deploy/user-data.sh` runs once at first boot: installs Docker and git, clones the public repo, runs `deploy/deploy.sh`
(build the image, start the container).

```bash
INSTANCE=$(aws ec2 run-instances --image-id $AMI --instance-type t4g.small --credit-specification CpuCredits=standard --key-name pitwall \
    --security-group-ids $SG --user-data file://deploy/user-data.sh \
    --metadata-options HttpTokens=required,HttpEndpoint=enabled \
    --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=16,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=pitwall}]' \
    --query 'Instances[0].InstanceId' --output text)
aws ec2 wait instance-running --instance-ids $INSTANCE
echo $INSTANCE
```

## 5. Elastic IP

```bash
ALLOC=$(aws ec2 allocate-address --domain vpc --query AllocationId --output text)
aws ec2 associate-address --instance-id $INSTANCE --allocation-id $ALLOC
IP=$(aws ec2 describe-addresses --allocation-ids $ALLOC --query 'Addresses[0].PublicIp' --output text)
echo "http://$IP"
```

## 6. Wait for the first build, then check it

The first boot builds the image (a few minutes). Watch it:

```bash
ssh -i ~/.ssh/pitwall.pem ec2-user@$IP 'sudo tail -f /var/log/cloud-init-output.log'
# stop with Ctrl-C once you see "pitwall is healthy"
curl http://$IP/_stcore/health          # prints: ok
```

Then the clean-browser test, **in a private window, ideally on another network (your phone)**:

- the page loads and a race picker appears; choose a 2025 race and a car; the verdict box and both charts render;
- switch races twice, toggle "Include traffic", open the "Assumptions and limitations" panel;
- tick "Add it to the comparison" with two identical tyres: you must get a message, not an error page;
- no file paths or stack traces anywhere.

## 7. Updating after a code change

```bash
git push                                  # from your laptop
ssh -i ~/.ssh/pitwall.pem ec2-user@$IP 'cd /opt/pitwall && sudo ./deploy/deploy.sh'
```

## 8. HTTPS (optional, not tested)

Plain HTTP on an IP is acceptable for a portfolio demo if the README says so. For HTTPS you need a domain pointing at
the Elastic IP, then on the instance (open port 443 in the security group first) replace the `-p 80:8501` mapping with a
Caddy container that gets a certificate automatically:

```bash
docker network create web
docker rm -f pitwall && docker run -d --name pitwall --network web --restart unless-stopped --memory 1200m pitwall:latest
docker run -d --name caddy --network web --restart unless-stopped -p 80:80 -p 443:443 -v caddy_data:/data \
    caddy:2 caddy reverse-proxy --from your.domain.example --to pitwall:8501
```

## 9. Tear it all down (stops the bill)

```bash
aws ec2 terminate-instances --instance-ids $INSTANCE
aws ec2 wait instance-terminated --instance-ids $INSTANCE
aws ec2 release-address --allocation-id $ALLOC
aws ec2 delete-security-group --group-id $SG
aws ec2 delete-key-pair --key-name pitwall && rm ~/.ssh/pitwall.pem
```
If you closed the shell and lost the variables, find them again:
`aws ec2 describe-instances --filters Name=tag:Name,Values=pitwall --query 'Reservations[].Instances[].InstanceId'`,
`aws ec2 describe-addresses`, `aws ec2 describe-security-groups --group-names pitwall`.
The budget stays (it costs nothing); delete it with `aws budgets delete-budget --account-id $ACCOUNT --budget-name pitwall-monthly`.

## 10. If something goes wrong

| Symptom | Look at |
|---|---|
| nothing at `http://$IP` after 10 minutes | `ssh ...` then `sudo tail -100 /var/log/cloud-init-output.log` |
| container restarts | `sudo docker logs --tail 80 pitwall`, `sudo docker ps -a` |
| killed for memory | `sudo docker stats --no-stream`; the container limit is 1200 MB, the instance has 2 GB |
| SSH refused / times out | your IP changed: `aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 22 --cidr NEW_IP/32` |
| build can't clone the repo | the GitHub repo must be public and `git push` done (the clone happens on the server) |

## What was and wasn't tested

Tested locally (macOS, Docker 28, arm64): the image builds (1.26 GB), the container is healthy in about 9 s, serves
HTTP 200, runs as a non-root user, the app executes inside it for 50 races, a session peaks at 471 MB, and
`deploy/deploy.sh` builds, starts and replaces the container twice in a row.
**Not tested:** every AWS command, the Amazon Linux install line in `deploy/user-data.sh`, and Docker on Amazon Linux 2023,
which has no buildx plugin, so `docker build` falls back to the classic builder (the Dockerfile uses only features it supports).
The server (`t4g.small`) is arm64 like the laptop it was tested on, so the image is the same architecture.

## Known limits to state

- The first visit after a restart fits the model (about 5 s); later visits reuse it (`st.cache_resource`).
- One process serves everyone; there is no database and no accounts.
- Only the cached races are available (50 of the 57 in the dataset); there is no live data.
- The data files are derived from the public OpenF1 API (see the README); the project is not affiliated with Formula 1.
