#!/bin/bash

#Usage Info
show_help() {
cat << EOF
  Usage: ${0##*/} [-e AWS ENVIRONMENT] [-s AWS CLOUDFORMATION STACK NAME] [-a APPLICATION NAME] [-i AMI ID ] [-r CLOUDFORMATION ROLE ARN]
  Create a CloudFormation stack with the specified options.

      -a  application name (app.example.com)
      -e  aws environment name (staging | prod)
      -r  aws role ARN to be assumed by CloudFormation
      -s  aws cloudformation stack name (app-example-env-stack)
      -i  aws AMI ID (ami-1234abc)
      -h  get usage info

EOF
}

# Parse options
while getopts ':e:s:a:i:r:h' option; do
  case $option in
    h  ) show_help >&2; exit;;
    e  ) e_flag=true; aws_environment=$OPTARG;;
    s  ) s_flag=true; cf_stack_name=$OPTARG;;
    a  ) a_flag=true; app_name=$OPTARG;;
    i  ) i_flag=true; ami_id=$OPTARG;;
    r  ) r_flag=true; role_arn=$OPTARG;;
    \? ) printf "\n%s\n" "  Invalid option: -$OPTARG" >&2; exit 1;;
    :  ) printf "\n%s\n\n%s\n" "  Option -$OPTARG requires an argument." "$(show_help)" >&2; exit 1;;
  esac
done

shift "$((OPTIND - 1))"

# Error if -e options is not included
if [[ -z "$e_flag" || -z "$s_flag" || -z "$a_flag" || -z "$i_flag" ]]; then
  printf "\n%s\n\n%s\n" "  One of the following options is missing." "$(show_help)" >&2
  exit 1
elif [[ -z "$e_flag" || ! "$aws_environment" =~ ("staging"|"prod") ]]; then
  printf "\n%s\n\n%s\n" "  A valid AWS environment must be specified." "$(show_help)" >&2
  exit 1
elif [[ -z "$s_flag" ]]; then
  printf "\n%s\n\n%s\n" "  A valid AWS stack name must be specified." "$(show_help)" >&2
  exit 1
elif [[ -z "$i_flag" ]]; then
  printf "\n%s\n\n%s\n" "  A valid Amazon Machine Image ID must be specified." "$(show_help)" >&2
  exit 1
elif [[ -z "$r_flag" ]]; then
  printf "\n%s\n\n%s\n" "  A valid AWS role ARN must be provided for CloudFormation to assume." "$(show_help)" >&2
  exit 1
fi

if [ "$aws_environment" == "staging" ]; then
  aws_profile="staging"
  param_path="./cloudformation/parameters/staging/$app_name-params.json"
elif [ "$aws_environment" == "prod" ]; then
  aws_profile="production-admin"
  param_path="./cloudformation/parameters/production/$app_name-params.json"
fi

template_url="https://s3-us-west-2.amazonaws.com/brivity-$aws_environment-cloudformation/templates/$app_name-cftemplate.yml"
template_path="../cloudformation/templates/$app_name-cftemplate.yml"
product_name="$(echo $app_name | cut -d "." -f2)"
service_name="$(echo $app_name | cut -d "." -f1)"

if [[ -z "$a_flag" || ! -f "$param_path" ]]; then
  printf "\n%s\n\n%s\n" "  A valid app name must be specified." "$(show_help)" >&2
  exit 1
fi

aws s3 cp "$template_path" s3://"$app_name"-"$aws_environment"-cloudformation/templates/"$app_name"-cftemplate.yml --profile "$aws_profile" && \
aws s3 cp "$param_path" s3://"$app_name"-"$aws_environment"-cloudformation/parameters/"$app_name"-params.json --profile "$aws_profile" && \
sed -i '' "s/AMI_ID/$ami_id/" "$param_path" && \
stackId=`aws cloudformation create-stack --profile "$aws_profile" --template-url "$template_url" \
--parameters file://"$param_path" --capabilities CAPABILITY_NAMED_IAM --stack-name="$cf_stack_name" \
--role-arn "$role_arn" --tags "[{\"Key\": \"Name\", \"Value\": \"$app_name\"}, {\"Key\": \"ProductName\", \"Value\": \"$product_name\"}, \
{\"Key\": \"ServiceName\", \"Value\": \"$service_name\"}, {\"Key\": \"EnvironmentName\", \"Value\": \"$aws_environment\"}]"`

if [ $? -eq 0 ]; then
  printf "\n%s\n%s\n" "successfully created" "$stackId"
  sed -i '' "s/$ami_id/AMI_ID/" "$param_path"
else
  printf "\n%s\n" "CloudFormation stack failed to create."
  sed -i '' "s/$ami_id/AMI_ID/" "$param_path"
  exit 1
fi
